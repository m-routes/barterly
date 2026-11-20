"""Deliverables for barter and hybrid gigs: from the agreement to the host's approval.

- At check-in, each item of the agreement's deliverables becomes one Deliverable per
  unit ("3 reels" → three), due on the stay's last day unless the host moves it.
- The talent submits a post link and/or files. A public post needs the collaboration
  label (#collab, #ad, the paid-partnership tag...): the talent confirms it, and where
  the platform shows the caption it's checked too. The host sees both.
- The host approves, or asks for changes (at most MAX_CHANGE_ROUNDS times; after that,
  approve or open a dispute).
- Escrow (hybrid gigs): once every deliverable is submitted, the 72-hour approval window
  runs from the last submission (escrow.auto_release). Approving them all releases it.
"""

import contextlib
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Exists, Max, OuterRef
from django.utils import timezone

from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.deliverables.models import (
    MAX_CHANGE_ROUNDS,
    Deliverable,
    Kind,
    Platform,
    PostStats,
    StatsSource,
    Status,
    Submission,
)
from apps.deliverables.stats.base import get_provider, has_disclosure
from apps.gigs.constants import DELIVERABLE_MODELS, DeliverableType
from apps.media.models import MediaFile, MediaStatus

B = BookingStatus
OPEN_FOR_WORK = (B.CHECKED_IN, B.DELIVERING, B.COMPLETED)
UNUSABLE_MEDIA = (MediaStatus.REJECTED, MediaStatus.QUARANTINED, MediaStatus.PENDING_UPLOAD)
MAX_FILES = 20
DUE_DATE_SLACK = timedelta(days=30)  # how long after the stay a due date may be

KIND_FOR = {
    DeliverableType.INSTAGRAM_REEL: Kind.REEL,
    DeliverableType.INSTAGRAM_STORY: Kind.STORY,
    DeliverableType.PHOTO_SET: Kind.PHOTO_SET,
    DeliverableType.GOOGLE_REVIEW: Kind.GOOGLE_REVIEW,
}
PLATFORM_FOR = {
    DeliverableType.INSTAGRAM_POST: Platform.INSTAGRAM,
    DeliverableType.INSTAGRAM_REEL: Platform.INSTAGRAM,
    DeliverableType.INSTAGRAM_STORY: Platform.INSTAGRAM,
    DeliverableType.YOUTUBE_VIDEO: Platform.YOUTUBE,
    DeliverableType.GOOGLE_REVIEW: Platform.GOOGLE,
}
# Published where the public sees it: needs the collaboration label.
PUBLIC_POSTS = {*PLATFORM_FOR, DeliverableType.BLOG_POST}


class DeliverableError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def _terms(booking: Booking) -> dict:
    agreement = getattr(booking, "agreement", None)
    version = agreement and agreement.current_version
    return version.terms if version else {}


def usage_rights(booking: Booking) -> dict | None:
    return _terms(booking).get("usage_rights")


def usable_until(booking: Booking, approved_at) -> date | None:
    rights = usage_rights(booking)
    if not rights or not approved_at:
        return None
    start = timezone.localdate(approved_at)
    months = start.month - 1 + int(rights["duration_months"])
    year, month = start.year + months // 12, months % 12 + 1
    from calendar import monthrange

    return date(year, month, min(start.day, monthrange(year, month)[1]))


# ---------- From the agreement ----------


def create_for(booking: Booking, now=None) -> list[Deliverable]:
    """One deliverable per unit of each spec item. Safe to call again."""
    if booking.gig.compensation_model not in DELIVERABLE_MODELS:
        return []
    now = now or timezone.now()
    existing = set(Deliverable.objects.filter(booking=booking).values_list("spec_index", "unit"))
    made = []
    for index, item in enumerate(_terms(booking).get("deliverables") or []):
        spec = item["type"]
        quantity = int(item["quantity"])
        label = DeliverableType(spec).label if spec in DeliverableType.values else spec
        for unit in range(1, quantity + 1):
            if (index, unit) in existing:
                continue
            made.append(
                Deliverable(
                    booking=booking,
                    spec_index=index,
                    unit=unit,
                    quantity=quantity,
                    spec_type=spec,
                    kind=KIND_FOR.get(spec, Kind.CUSTOM),
                    platform=PLATFORM_FOR.get(spec, Platform.OTHER),
                    title=f"{label} {unit} of {quantity}" if quantity > 1 else label,
                    notes=item.get("notes") or "",
                    due_date=booking.end_date,
                    disclosure_required=spec in PUBLIC_POSTS,
                    created_at=now,
                )
            )
    Deliverable.objects.bulk_create(made, ignore_conflicts=True)
    return made


def on_checked_in(event) -> None:
    booking_id = event.payload.get("booking_id")
    if booking_id:
        booking = Booking.objects.select_related("gig", "agreement__current_version").get(
            pk=booking_id
        )
        create_for(booking, now=event.occurred_at)


def for_booking(booking: Booking) -> list[Deliverable]:
    if booking.status in OPEN_FOR_WORK and not booking.deliverables.exists():
        create_for(booking)  # checked in before deliverables were tracked
    return list(
        Deliverable.objects.filter(booking=booking).prefetch_related("submissions__files", "stats")
    )


# ---------- Submitting ----------


def _notify(name: str, deliverable: Deliverable, now, *, to: str, key: str, **extra) -> None:
    booking = deliverable.booking
    publish(
        DomainEvent(
            name,
            {
                "booking_id": str(booking.pk),
                "deliverable_id": str(deliverable.pk),
                "deliverable": deliverable.title,
                "gig_title": booking.gig.title,
                "talent_id": str(booking.talent_id),
                "vendor_id": str(booking.vendor_id),
                "dedup_key": f"{name}:{deliverable.pk}:{key}",
                "notify": [to],
                **extra,
            },
            occurred_at=now,
        )
    )


def submit(
    deliverable_id,
    *,
    talent,
    post_url: str = "",
    file_ids=(),
    note: str = "",
    disclosure_confirmed: bool = False,
    request=None,
    now=None,
) -> Submission:
    now = now or timezone.now()
    post_url = post_url.strip()
    file_ids = list(dict.fromkeys(str(f) for f in file_ids))[:MAX_FILES]
    if not post_url and not file_ids:
        raise DeliverableError("Add the post's link, or upload the files.", 400)
    with transaction.atomic():
        deliverable = (
            Deliverable.objects.select_for_update(of=("self",))
            .select_related("booking__gig", "booking__talent__talent_profile")
            .get(pk=deliverable_id, booking__talent=talent)
        )
        if deliverable.booking.status not in OPEN_FOR_WORK:
            raise DeliverableError("Hand in work once you've checked in.")
        if deliverable.status == Status.APPROVED:
            raise DeliverableError("This one's approved already.")
        if deliverable.disclosure_required and not disclosure_confirmed:
            raise DeliverableError(
                "Add the collaboration label (#collab or #ad, or Instagram's paid "
                "partnership tag) to the post, then confirm it.",
                400,
            )
        files = list(
            MediaFile.objects.filter(pk__in=file_ids, owner=talent).exclude(
                status__in=UNUSABLE_MEDIA
            )
        )
        if len(files) != len(file_ids):
            raise DeliverableError("Some of these uploads can't be used. Upload them again.", 400)
        version = (deliverable.submissions.aggregate(v=Max("version"))["v"] or 0) + 1
        submission = Submission.objects.create(
            deliverable=deliverable,
            version=version,
            post_url=post_url,
            note=note.strip()[:500],
            disclosure_confirmed=disclosure_confirmed,
            submitted_at=now,
        )
        submission.files.set(files)
        deliverable.status, deliverable.submitted_at = Status.SUBMITTED, now
        deliverable.save(update_fields=["status", "submitted_at", "updated_at"])
        log_action(
            actor=talent,
            action="deliverables.submitted",
            obj=deliverable,
            after={
                "version": version,
                "post_url": post_url,
                "files": len(files),
                "disclosure_confirmed": disclosure_confirmed,
            },
            request=request,
        )
        _notify("deliverables.submitted", deliverable, now, to="vendor", key=str(version))
        if all_handed_in(deliverable.booking):
            _notify(
                "deliverables.all_submitted", deliverable, now, to="vendor", key=now.isoformat()
            )
    if post_url:
        transaction.on_commit(lambda: refresh_stats(deliverable.pk, submission_id=submission.pk))
    return submission


def all_handed_in(booking: Booking) -> bool:
    rows = Deliverable.objects.filter(booking=booking)
    return (
        rows.exists()
        and not rows.filter(status__in=(Status.PENDING, Status.CHANGES_REQUESTED)).exists()
    )


# ---------- The host's review ----------


def review(
    deliverable_id, *, vendor, approve: bool, note: str = "", request=None, now=None
) -> Deliverable:
    now = now or timezone.now()
    if not approve and not note.strip():
        raise DeliverableError("Say what needs to change.", 400)
    with transaction.atomic():
        deliverable = (
            Deliverable.objects.select_for_update(of=("self",))
            .select_related("booking__gig")
            .get(pk=deliverable_id, booking__vendor=vendor)
        )
        if deliverable.status != Status.SUBMITTED:
            raise DeliverableError("There's no submission waiting for you on this one.")
        latest = deliverable.submissions.first()
        if not approve and deliverable.change_rounds >= MAX_CHANGE_ROUNDS:
            raise DeliverableError(
                "You've used both rounds of changes. Approve it, or open a dispute on the booking."
            )
        latest.review = "approved" if approve else "changes"
        latest.review_note, latest.reviewed_at = note.strip()[:1000], now
        latest.save(update_fields=["review", "review_note", "reviewed_at"])
        if approve:
            deliverable.status, deliverable.approved_at = Status.APPROVED, now
        else:
            deliverable.status = Status.CHANGES_REQUESTED
            deliverable.change_rounds += 1
        deliverable.save()
        log_action(
            actor=vendor,
            action=f"deliverables.{deliverable.status}",
            obj=deliverable,
            after={
                "version": latest.version,
                "note": latest.review_note,
                "change_rounds": deliverable.change_rounds,
            },
            request=request,
        )
        if approve:
            _notify("deliverables.approved", deliverable, now, to="talent", key="approved")
        else:
            _notify(
                "deliverables.changes_requested",
                deliverable,
                now,
                to="talent",
                key=str(deliverable.change_rounds),
                note=latest.review_note,
                rounds_left=MAX_CHANGE_ROUNDS - deliverable.change_rounds,
            )
    if approve and _all_approved(deliverable.booking):
        _release_escrow(deliverable.booking, vendor, now)
    return deliverable


def _all_approved(booking: Booking) -> bool:
    rows = Deliverable.objects.filter(booking=booking)
    return rows.exists() and not rows.exclude(status=Status.APPROVED).exists()


def _release_escrow(booking: Booking, vendor, now) -> None:
    """Every deliverable approved: release a hybrid gig's stipend. If it can't happen now
    (the kill switch, say), the auto-release job tries again."""
    from apps.money import escrow
    from apps.money.models import Escrow, EscrowStatus

    if Escrow.objects.filter(booking=booking, status=EscrowStatus.HELD).exists():
        with contextlib.suppress(escrow.EscrowError):
            escrow.release(booking.pk, by="vendor", actor=vendor, now=now)


def set_due_date(deliverable_id, *, vendor, due_date: date, request=None, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        deliverable = (
            Deliverable.objects.select_for_update(of=("self",))
            .select_related("booking__gig")
            .get(pk=deliverable_id, booking__vendor=vendor)
        )
        booking = deliverable.booking
        if deliverable.status == Status.APPROVED:
            raise DeliverableError("This one's approved already.")
        if not booking.start_date <= due_date <= booking.end_date + DUE_DATE_SLACK:
            raise DeliverableError("Pick a date during the stay or within 30 days after it.", 400)
        before = str(deliverable.due_date)
        deliverable.due_date = due_date
        deliverable.save(update_fields=["due_date", "updated_at"])
        log_action(
            actor=vendor,
            action="deliverables.due_date_changed",
            obj=deliverable,
            before={"due_date": before},
            after={"due_date": str(due_date)},
            request=request,
        )
        _notify(
            "deliverables.due_date_changed",
            deliverable,
            now,
            to="talent",
            key=str(due_date),
            due=due_date.strftime("%d %b"),
        )
    return deliverable


# ---------- Escrow's approval window ----------


def release_window(booking: Booking):
    """For escrow.auto_release: None when the booking has no tracked deliverables (the
    single-submission flow applies); else ("approved", at), ("waiting", since) when
    everything's handed in and the host hasn't finished, or ("open", None)."""
    rows = Deliverable.objects.filter(booking=booking)
    if not rows.exists():
        return None
    if not rows.exclude(status=Status.APPROVED).exists():
        return "approved", rows.aggregate(at=Max("approved_at"))["at"]
    if rows.filter(status__in=(Status.PENDING, Status.CHANGES_REQUESTED)).exists():
        return "open", None
    return "waiting", rows.aggregate(at=Max("submitted_at"))["at"]


# ---------- Stats ----------


def _handle(deliverable: Deliverable) -> str:
    profile = getattr(deliverable.booking.talent, "talent_profile", None)
    return getattr(profile, "instagram_handle", "") or ""


def refresh_stats(deliverable_id, *, submission_id=None, now=None) -> PostStats | None:
    """Ask the platform for the post's numbers (and, on a new submission, whether its
    caption carries the label). Nothing found: nothing recorded."""
    deliverable = Deliverable.objects.select_related("booking__talent__talent_profile").get(
        pk=deliverable_id
    )
    latest = deliverable.submissions.first()
    if latest is None or not latest.post_url:
        return None
    found = get_provider().stats_for(latest.post_url, handle=_handle(deliverable))
    if found is None:
        return None
    if submission_id and found.caption is not None:
        Submission.objects.filter(pk=submission_id).update(
            disclosure_detected=has_disclosure(found.caption)
        )
    return PostStats.objects.create(
        deliverable=deliverable,
        source=found.source,
        views=found.views,
        likes=found.likes,
        comments=found.comments,
        captured_at=now or timezone.now(),
    )


def refresh_all(now) -> dict[str, int]:
    """Job: fresh numbers for posts handed in, at most once every 20 hours each."""
    recent = now - timedelta(hours=20)
    fresh = PostStats.objects.filter(
        deliverable=OuterRef("pk"),
        captured_at__gt=recent,
        source__in=(StatsSource.INSTAGRAM, StatsSource.YOUTUBE),
    )
    rows = (
        Deliverable.objects.filter(status__in=(Status.SUBMITTED, Status.APPROVED))
        .exclude(Exists(fresh))
        .filter(submissions__post_url__gt="")
        .distinct()
        .values_list("pk", flat=True)[:500]
    )
    updated = sum(1 for pk in list(rows) if refresh_stats(pk, now=now))
    return {"updated": updated}


def report_stats(
    deliverable_id,
    *,
    talent,
    views=None,
    likes=None,
    comments=None,
    screenshot_id,
    request=None,
    now=None,
) -> PostStats:
    """Numbers the talent types in, with a screenshot as evidence. Shown as
    self-reported wherever they appear."""
    if views is None and likes is None and comments is None:
        raise DeliverableError("Enter at least one number.", 400)
    deliverable = Deliverable.objects.get(pk=deliverable_id, booking__talent=talent)
    if deliverable.status not in (Status.SUBMITTED, Status.APPROVED):
        raise DeliverableError("Submit the post first.")
    screenshot = (
        MediaFile.objects.filter(pk=screenshot_id, owner=talent, kind="photo")
        .exclude(status__in=UNUSABLE_MEDIA)
        .first()
    )
    if screenshot is None:
        raise DeliverableError("Upload a screenshot of the numbers.", 400)
    stats = PostStats.objects.create(
        deliverable=deliverable,
        source=StatsSource.MANUAL,
        views=views,
        likes=likes,
        comments=comments,
        screenshot=screenshot,
        reported_by=talent,
        captured_at=now or timezone.now(),
    )
    log_action(
        actor=talent,
        action="deliverables.stats_reported",
        obj=deliverable,
        after={"views": views, "likes": likes, "comments": comments},
        request=request,
    )
    return stats


# ---------- Reminders ----------


def send_reminders(now) -> dict[str, int]:
    """Job: due in two days, due today, and overdue (once, the day after)."""
    today = timezone.localdate(now)
    sent = 0
    open_rows = Deliverable.objects.filter(
        status__in=(Status.PENDING, Status.CHANGES_REQUESTED),
        booking__status__in=OPEN_FOR_WORK,
    ).select_related("booking__gig")
    for when, label in (
        (today + timedelta(days=2), "in_two_days"),
        (today, "today"),
        (today - timedelta(days=1), "overdue"),
    ):
        for deliverable in open_rows.filter(due_date=when):
            _notify(
                f"deliverables.due_{label}",
                deliverable,
                now,
                to="talent",
                key=str(deliverable.due_date),
                due=deliverable.due_date.strftime("%d %b"),
            )
            sent += 1
    return {"reminders": sent}
