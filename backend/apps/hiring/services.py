"""Vendor hiring actions. Status changes go through applications.services (and so the
one transition table in apps.bookings.lifecycle); this module adds the hiring details
around them: rejection reasons, bulk actions, auto-reject rules, notes, tags and
interviews."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.applications import services as applications
from apps.applications.constants import ApplicationStatus as A
from apps.applications.models import Application
from apps.bookings.lifecycle import Actor
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.hiring import autoreject
from apps.hiring.models import (
    ACTIVE_INTERVIEW,
    MAX_SLOTS,
    MAX_TAGS,
    ApplicationNote,
    ApplicationTag,
    Interview,
    InterviewSlot,
    InterviewStatus,
)
from apps.hiring.templates import VENDOR_REASONS, RejectionReason, compose

IST = ZoneInfo("Asia/Kolkata")
MIN_NOTICE = timedelta(hours=1)
MAX_AHEAD = timedelta(days=60)
DAY_BEFORE = timedelta(days=1)
HOUR_BEFORE = timedelta(hours=1)
MAX_BULK = 100


class HiringError(Exception):
    """A hiring action can't happen (the message says why)."""


def ist(moment: datetime | None) -> str:
    """'Mon 17 Nov 2026, 4:30 PM IST' for a UTC-stored time."""
    if moment is None:
        return ""
    local = moment.astimezone(IST)
    return f"{local:%a %d %b %Y}, {local.strftime('%I:%M %p').lstrip('0')} IST"


# ---------- Status moves ----------


def _set_rejection_code(application_id, code: str) -> None:
    Application.objects.filter(pk=application_id).update(rejection_code=code)


def reject(application_id, *, user, code: str, message: str = "", actor=Actor.VENDOR, request=None):
    if actor == Actor.VENDOR and code not in VENDOR_REASONS:
        raise HiringError("Pick one of the rejection reasons.")
    with transaction.atomic():
        try:
            application = applications.transition(
                application_id,
                A.REJECTED,
                actor=actor,
                user=user,
                reason=compose(code, message),
                request=request,
            )
        except applications.InvalidApplicationTransition as exc:
            raise HiringError(str(exc)) from exc
        _set_rejection_code(application_id, code)
        application.rejection_code = code
    return application


def move(application_id, to: str, *, vendor, code: str = "", message: str = "", request=None):
    """Shortlist, move to interview, offer or reject, as the gig's vendor."""
    if to == A.REJECTED:
        return reject(application_id, user=vendor, code=code, message=message, request=request)
    try:
        return applications.transition(
            application_id, to, actor=Actor.VENDOR, user=vendor, reason=message, request=request
        )
    except applications.InvalidApplicationTransition as exc:
        raise HiringError(str(exc)) from exc


@dataclass
class BulkResult:
    id: str
    ok: bool
    status: str = ""
    error: str = ""


def bulk(gig, ids, action: str, *, vendor, code: str = "", message: str = "", request=None):
    """Shortlist or reject many applications of one gig. Each one is its own change;
    the results say which worked and why the others didn't."""
    if len(ids) > MAX_BULK:
        raise HiringError(f"At most {MAX_BULK} at a time.")
    owned = set(
        str(pk)
        for pk in Application.objects.filter(gig=gig, pk__in=ids).values_list("pk", flat=True)
    )
    to = A.SHORTLISTED if action == "shortlist" else A.REJECTED
    results = []
    for pk in dict.fromkeys(str(i) for i in ids):
        if pk not in owned:
            results.append(BulkResult(pk, False, error="No such application on this gig."))
            continue
        try:
            done = move(pk, to, vendor=vendor, code=code, message=message, request=request)
            results.append(BulkResult(pk, True, status=done.status))
        except HiringError as exc:
            results.append(BulkResult(pk, False, error=str(exc)))
    return results


def run_auto_reject(application, profile) -> bool:
    """Called when an application is submitted (inside its transaction). Rejects it at
    once, saying why, if it misses any of the gig's auto-reject rules."""
    missing = autoreject.failures(application, profile)
    if not missing:
        return False
    applications.move(
        applications.lock(application.pk),
        A.REJECTED,
        actor=Actor.SYSTEM,
        reason=compose(RejectionReason.AUTO_RULE, autoreject.explain(missing)),
    )
    _set_rejection_code(application.pk, RejectionReason.AUTO_RULE)
    return True


# ---------- Notes and tags (vendor-private) ----------


def add_note(application, *, author, body: str) -> ApplicationNote:
    body = body.strip()
    if not body:
        raise HiringError("Write something.")
    return ApplicationNote.objects.create(application=application, author=author, body=body)


def set_tags(application, labels: list[str]) -> list[str]:
    cleaned = sorted({label.strip().lower() for label in labels if label.strip()})
    if len(cleaned) > MAX_TAGS:
        raise HiringError(f"At most {MAX_TAGS} tags.")
    if any(len(label) > 30 for label in cleaned):
        raise HiringError("Keep each tag under 30 characters.")
    with transaction.atomic():
        ApplicationTag.objects.filter(application=application).exclude(label__in=cleaned).delete()
        for label in cleaned:
            ApplicationTag.objects.get_or_create(application=application, label=label)
    return cleaned


# ---------- Interviews ----------


def _check_link(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise HiringError("Paste the full video link, starting with https://")
    return url.strip()


def _check_slots(slots: list[datetime], now: datetime) -> list[datetime]:
    if not 1 <= len(slots) <= MAX_SLOTS:
        raise HiringError(f"Offer between 1 and {MAX_SLOTS} times.")
    utc = sorted({s.astimezone(UTC) for s in slots})
    if len(utc) != len(slots):
        raise HiringError("The times must be different.")
    for slot in utc:
        if slot < now + MIN_NOTICE:
            raise HiringError(f"{ist(slot)} is too soon: give at least an hour's notice.")
        if slot > now + MAX_AHEAD:
            raise HiringError(f"{ist(slot)} is more than {MAX_AHEAD.days} days away.")
    return utc


def _payload(interview: Interview) -> dict:
    application = interview.application
    return {
        "interview_id": str(interview.pk),
        "application_id": str(application.pk),
        "gig_id": str(application.gig_id),
        "gig_title": application.gig.title,
        "talent_id": str(application.talent_id),
        "vendor_id": str(application.gig.vendor_id),
        "status": interview.status,
        "starts_at": interview.starts_at,
        "starts_at_ist": ist(interview.starts_at),
        "duration_minutes": interview.duration_minutes,
        "video_link": interview.video_link if interview.status == InterviewStatus.SCHEDULED else "",
        "slots_ist": [ist(s.starts_at) for s in interview.slots.all()],
    }


def _announce(
    interview: Interview, name: str, *, user=None, request=None, extra: dict | None = None
):
    log_action(
        actor=user,
        action=f"interview.{name}",
        obj=interview,
        after={"status": interview.status, "starts_at": interview.starts_at, **(extra or {})},
        request=request,
    )
    publish(DomainEvent(f"interview.{name}", {**_payload(interview), **(extra or {})}))


def active_interview(application) -> Interview | None:
    return (
        Interview.objects.filter(application=application, status__in=ACTIVE_INTERVIEW)
        .prefetch_related("slots")
        .first()
    )


def propose_interview(
    application_id,
    *,
    vendor,
    slots: list[datetime],
    video_link: str,
    duration_minutes: int = 30,
    note: str = "",
    request=None,
    now=None,
) -> Interview:
    """The vendor offers up to three times and a video link. Moves the application to
    the interview stage if needed, and replaces any interview still being arranged."""
    now = now or timezone.now()
    link = _check_link(video_link)
    times = _check_slots(slots, now)
    with transaction.atomic():
        application = applications.lock(application_id)
        if application.gig.vendor_id != vendor.pk:
            raise Application.DoesNotExist
        if application.status in (A.APPLIED, A.SHORTLISTED):
            try:
                applications.move(
                    application, A.INTERVIEW, actor=Actor.VENDOR, user=vendor, now=now
                )
            except applications.InvalidApplicationTransition as exc:
                raise HiringError(str(exc)) from exc
        if application.status != A.INTERVIEW:
            raise HiringError(
                f"A {application.get_status_display().lower()} application can't be interviewed."
            )
        for old in Interview.objects.select_for_update().filter(
            application=application, status__in=ACTIVE_INTERVIEW
        ):
            old.status = InterviewStatus.CANCELLED
            old.save(update_fields=["status", "updated_at"])
        interview = Interview.objects.create(
            application=application,
            video_link=link,
            duration_minutes=duration_minutes,
            note=note.strip(),
        )
        InterviewSlot.objects.bulk_create(
            InterviewSlot(interview=interview, starts_at=t) for t in times
        )
        _announce(interview, "proposed", user=vendor, request=request)
    return interview


def _locked_interview(application_id) -> Interview:
    interview = (
        Interview.objects.select_for_update()
        .select_related("application__gig")
        .filter(application_id=application_id, status__in=ACTIVE_INTERVIEW)
        .first()
    )
    if interview is None:
        raise HiringError("There's no interview being arranged for this application.")
    return interview


def pick_slot(application_id, slot_id, *, talent, request=None, now=None) -> Interview:
    now = now or timezone.now()
    with transaction.atomic():
        interview = _locked_interview(application_id)
        if interview.application.talent_id != talent.pk:
            raise Application.DoesNotExist
        if interview.status != InterviewStatus.PROPOSED:
            raise HiringError("This interview isn't waiting for you to pick a time.")
        slot = interview.slots.filter(pk=slot_id).first()
        if slot is None:
            raise HiringError("Pick one of the offered times.")
        if slot.starts_at <= now:
            raise HiringError("That time has passed. Ask the host for new times.")
        interview.chosen_slot = slot
        interview.starts_at = slot.starts_at
        interview.status = InterviewStatus.SCHEDULED
        interview.save()
        _announce(interview, "scheduled", user=talent, request=request)
    return interview


def request_new_times(application_id, *, talent, note: str = "", request=None) -> Interview:
    with transaction.atomic():
        interview = _locked_interview(application_id)
        if interview.application.talent_id != talent.pk:
            raise Application.DoesNotExist
        if interview.status != InterviewStatus.PROPOSED:
            raise HiringError("This interview isn't waiting for you to pick a time.")
        interview.status = InterviewStatus.NEW_TIMES_REQUESTED
        interview.save(update_fields=["status", "updated_at"])
        _announce(
            interview,
            "new_times_requested",
            user=talent,
            request=request,
            extra={"note": note.strip()},
        )
    return interview


def cancel_interview(application_id, *, vendor, reason: str = "", request=None) -> Interview:
    with transaction.atomic():
        interview = _locked_interview(application_id)
        if interview.application.gig.vendor_id != vendor.pk:
            raise Application.DoesNotExist
        interview.status = InterviewStatus.CANCELLED
        interview.save(update_fields=["status", "updated_at"])
        _announce(
            interview, "cancelled", user=vendor, request=request, extra={"reason": reason.strip()}
        )
    return interview


def close_interviews_when_application_moves_on(event: DomainEvent) -> None:
    """An offer, rejection, withdrawal or expiry ends any interview still active."""
    if event.payload.get("to") == A.INTERVIEW or event.payload.get("from") != A.INTERVIEW:
        return
    Interview.objects.filter(
        application_id=event.payload["application_id"], status__in=ACTIVE_INTERVIEW
    ).update(status=InterviewStatus.CANCELLED, updated_at=timezone.now())


def send_reminders(now) -> dict[str, int]:
    """Scheduled job: remind both sides a day and an hour before. Idempotent: each
    reminder is marked sent under a row lock, so reruns send nothing twice."""
    sent = {"day": 0, "hour": 0}
    upcoming = Interview.objects.filter(
        status=InterviewStatus.SCHEDULED, starts_at__gt=now, starts_at__lte=now + DAY_BEFORE
    ).values_list("pk", flat=True)
    for pk in list(upcoming):
        with transaction.atomic():
            interview = (
                Interview.objects.select_for_update().select_related("application__gig").get(pk=pk)
            )
            if interview.status != InterviewStatus.SCHEDULED or interview.starts_at <= now:
                continue
            left = interview.starts_at - now
            if left <= HOUR_BEFORE and interview.hour_reminder_sent_at is None:
                interview.hour_reminder_sent_at = now
                interview.day_reminder_sent_at = interview.day_reminder_sent_at or now
                interview.save(
                    update_fields=["hour_reminder_sent_at", "day_reminder_sent_at", "updated_at"]
                )
                publish(
                    DomainEvent("interview.reminder_hour", _payload(interview), occurred_at=now)
                )
                sent["hour"] += 1
            elif left > HOUR_BEFORE and interview.day_reminder_sent_at is None:
                interview.day_reminder_sent_at = now
                interview.save(update_fields=["day_reminder_sent_at", "updated_at"])
                publish(DomainEvent("interview.reminder_day", _payload(interview), occurred_at=now))
                sent["day"] += 1
    return sent


def timeline(application) -> list[dict]:
    """The application's status changes as the applicant may see them: when, what,
    and the reason given. Nothing about who in the vendor's team made the change."""
    from apps.common.models import AuditLog

    entries = AuditLog.objects.filter(
        object_type="applications.application", object_id=str(application.pk)
    ).order_by("created_at")
    shown = []
    for entry in entries:
        status = (entry.after or {}).get("status")
        if (
            not status
            or not entry.action.startswith("application.")
            or entry.action.endswith("_stale")
        ):
            continue
        shown.append(
            {
                "status": status,
                "at": entry.created_at,
                "reason": (entry.after or {}).get("status_reason", ""),
            }
        )
    return shown
