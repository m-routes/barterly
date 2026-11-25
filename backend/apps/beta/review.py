"""The weekly review of every dispute and safety report (docs/beta/weekly-review.md).

Every booking dispute, reported chat message and reported review raised in a week gets
a SafetyReview row once the trust team has looked at it. Items from past weeks without
one are "overdue": the ops_backlog job counts them, and monitoring alerts.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.beta.models import ReviewKind, ReviewOutcome, SafetyReview
from apps.common.services.audit import log_action

# How far back "overdue" looks; older items are out of the beta's scope.
LOOKBACK_WEEKS = 12


@dataclass
class Item:
    kind: str
    object_id: str
    raised_at: datetime
    summary: str
    link: str
    review: SafetyReview | None = None

    @property
    def kind_label(self) -> str:
        return ReviewKind(self.kind).label


def week_of(day: date) -> date:
    """The Monday of `day`'s week."""
    return day - timedelta(days=day.weekday())


def this_week(now=None) -> date:
    return week_of(timezone.localdate(now or timezone.now()))


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(start, time.min), tz),
        timezone.make_aware(datetime.combine(end, time.min), tz),
    )


def _admin_link(name: str, pk) -> str:
    try:
        return reverse(f"admin:{name}_change", args=[pk])
    except NoReverseMatch:
        return ""


def _raised(start: datetime, end: datetime) -> list[Item]:
    from apps.bookings.lifecycle import BookingStatus
    from apps.bookings.models import BookingEvent
    from apps.chat.models import MessageReport
    from apps.reviews.models import ReviewReport

    items: list[Item] = []
    disputes = BookingEvent.objects.filter(
        to_state=BookingStatus.DISPUTED, created_at__gte=start, created_at__lt=end
    ).order_by("created_at")
    for event in disputes:
        items.append(
            Item(
                ReviewKind.DISPUTE,
                str(event.booking_id),
                event.created_at,
                (event.reason or "")[:200],
                _admin_link("bookings_booking", event.booking_id),
            )
        )
    for report in MessageReport.objects.filter(created_at__gte=start, created_at__lt=end):
        items.append(
            Item(
                ReviewKind.CHAT_REPORT,
                str(report.pk),
                report.created_at,
                f"{report.get_reason_display()}. {report.note}".strip()[:200],
                _admin_link("chat_messagereport", report.pk),
            )
        )
    for report in ReviewReport.objects.filter(created_at__gte=start, created_at__lt=end):
        items.append(
            Item(
                ReviewKind.REVIEW_REPORT,
                str(report.pk),
                report.created_at,
                f"{report.get_reason_display()}. {report.note}".strip()[:200],
                _admin_link("reviews_reviewreport", report.pk),
            )
        )
    return items


def _attach_reviews(items: list[Item]) -> list[Item]:
    keys = {(i.kind, i.object_id) for i in items}
    found = {
        (r.kind, r.object_id): r
        for r in SafetyReview.objects.filter(object_id__in={k[1] for k in keys}).select_related(
            "reviewed_by"
        )
    }
    for item in items:
        item.review = found.get((item.kind, item.object_id))
    return items


def items_for(week: date) -> list[Item]:
    """Everything raised in the week starting `week` (a Monday), oldest first."""
    start, end = _bounds(week, week + timedelta(days=7))
    items = _attach_reviews(_raised(start, end))
    return sorted(items, key=lambda i: i.raised_at)


def overdue(now=None) -> list[Item]:
    """Unreviewed items from before this week (within LOOKBACK_WEEKS)."""
    current = this_week(now)
    start, end = _bounds(current - timedelta(weeks=LOOKBACK_WEEKS), current)
    return [i for i in _attach_reviews(_raised(start, end)) if i.review is None]


def record(
    kind: str, object_id: str, *, outcome: str, notes: str, by, week: date, request=None
) -> SafetyReview:
    if kind not in ReviewKind.values:
        raise ValueError("Unknown kind.")
    if outcome not in ReviewOutcome.values:
        raise ValueError("Choose an outcome.")
    if outcome != ReviewOutcome.NO_ACTION and not notes.strip():
        raise ValueError("Say what was done.")
    with transaction.atomic():
        before = SafetyReview.objects.filter(kind=kind, object_id=object_id).first()
        review, _ = SafetyReview.objects.update_or_create(
            kind=kind,
            object_id=object_id,
            defaults={
                "outcome": outcome,
                "notes": notes.strip(),
                "reviewed_by": by,
                "reviewed_at": timezone.now(),
                "week": week,
            },
        )
        log_action(
            actor=by,
            action="beta.safety_reviewed",
            obj=review,
            before={"outcome": before.outcome} if before else None,
            after={"kind": kind, "object_id": object_id, "outcome": outcome},
            request=request,
        )
    return review
