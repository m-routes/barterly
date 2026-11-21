"""Reputation: what others see about someone on one side (talent or host).

- average rating and number of published reviews about them;
- completion rate: of their bookings that ended, the share they completed (not a
  no-show, not cancelled late by them);
- response time: the median minutes they took to answer chat messages, last 90 days;
- badges, from the rules in settings (apps.reviews.badges).

Recomputed when a booking or review changes for them, and nightly.
"""

import statistics
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Avg, Count, Exists, OuterRef
from django.utils import timezone

from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking, BookingEvent, Cancellation, CancellationEffect
from apps.gigs.constants import DELIVERABLE_MODELS, CompensationModel
from apps.reviews import badges
from apps.reviews.models import Reputation, Review, ReviewStatus, Side

COMPLETED = (BookingStatus.COMPLETED, BookingStatus.REVIEWED)
RESPONSE_WINDOW = timedelta(days=90)
MAX_MESSAGES = 3000
CLEAN_MIN_RATING = 4

RECOMPUTE_ON = (
    "booking.completed",
    "booking.no_show",
    "booking.cancelled",
    "booking.disputed",
    "booking.reviewed",
    "reviews.published",
    "reviews.removed",
)


def _bookings(user_id, side: str):
    field = "talent_id" if side == Side.TALENT else "vendor_id"
    return Booking.objects.filter(**{field: user_id})


def published_about(user_id, side: str):
    return Review.objects.filter(
        subject_id=user_id, subject_side=side, status=ReviewStatus.PUBLISHED
    )


def response_minutes(user_id, now=None) -> int | None:
    """Median minutes from someone else's message to this person's next one in the same
    conversation (a run of messages counts from its first), last 90 days."""
    from apps.chat.models import Message

    now = now or timezone.now()
    messages = (
        Message.objects.filter(
            conversation__in=Message.objects.filter(sender_id=user_id).values("conversation"),
            created_at__gte=now - RESPONSE_WINDOW,
        )
        .order_by("conversation_id", "seq")
        .values_list("conversation_id", "sender_id", "created_at")[:MAX_MESSAGES]
    )
    waits: list[float] = []
    current, waiting_since = None, None
    for conversation, sender, at in messages:
        if conversation != current:
            current, waiting_since = conversation, None
        if str(sender) != str(user_id):
            waiting_since = waiting_since or at
        elif waiting_since is not None:
            waits.append((at - waiting_since).total_seconds() / 60)
            waiting_since = None
    return round(statistics.median(waits)) if waits else None


def metrics_for(user_id, side: str) -> dict:
    from apps.profiles.models import TalentProfile
    from apps.verification.constants import BadgeKind
    from apps.verification.models import Badge

    bookings = _bookings(user_id, side)
    completed = bookings.filter(status__in=COMPLETED)
    reviews = published_about(user_id, side)
    summary = reviews.aggregate(avg=Avg("rating"), n=Count("id"))
    no_shows = bookings.filter(status=BookingStatus.NO_SHOW).count() if side == Side.TALENT else 0
    by = "talent" if side == Side.TALENT else "vendor"
    late = Cancellation.objects.filter(
        booking__in=bookings,
        by=by,
        effect__in=(CancellationEffect.LATE, CancellationEffect.LAST_MINUTE),
    ).count()
    disputed = BookingEvent.objects.filter(booking=OuterRef("pk"), to_state=BookingStatus.DISPUTED)
    poor_review = Review.objects.filter(
        booking=OuterRef("pk"),
        subject_id=user_id,
        status__in=(ReviewStatus.PUBLISHED, ReviewStatus.REMOVED),
        rating__lt=CLEAN_MIN_RATING,
    )
    removed_review = Review.objects.filter(
        booking=OuterRef("pk"), author_id=user_id, status=ReviewStatus.REMOVED
    )
    clean = (
        completed.annotate(d=Exists(disputed), p=Exists(poor_review), r=Exists(removed_review))
        .filter(d=False, p=False, r=False)
        .count()
    )
    done = completed.count()
    ended = done + no_shows + late
    average = summary["avg"]
    return {
        "review_count": summary["n"],
        "rating_average": float(round(Decimal(str(average)), 2)) if average is not None else None,
        "completed": done,
        "completed_volunteer_gigs": completed.filter(
            gig__compensation_model=CompensationModel.VOLUNTEER
        ).count(),
        "completed_content_gigs": completed.filter(
            gig__compensation_model__in=DELIVERABLE_MODELS
        ).count(),
        "clean_gigs": clean,
        "no_shows": no_shows,
        "late_cancellations": late,
        "disputes": bookings.filter(Exists(disputed)).count(),
        "completion_rate": round(100 * done / ended) if ended else None,
        "id_verified": int(
            Badge.objects.filter(
                user_id=user_id, kind=BadgeKind.ID_VERIFIED, revoked_at__isnull=True
            ).exists()
        ),
        "instagram_linked": int(
            side == Side.TALENT
            and TalentProfile.objects.filter(user_id=user_id).exclude(instagram_handle="").exists()
        ),
    }


def recompute(user_id, side: str, now=None) -> Reputation:
    metrics = metrics_for(user_id, side)
    average = metrics["rating_average"]
    with transaction.atomic():
        record, _ = Reputation.objects.select_for_update().get_or_create(user_id=user_id, side=side)
        record.rating_average = (
            None
            if average is None
            else Decimal(str(average)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        record.review_count = metrics["review_count"]
        record.completion_rate = metrics["completion_rate"]
        record.response_minutes = response_minutes(user_id, now=now)
        record.badges = badges.award(side, metrics)
        record.metrics = metrics
        record.save()
    return record


def on_event(event) -> None:
    payload = event.payload
    if event.name.startswith("reviews."):
        if payload.get("subject_id") and payload.get("subject_side"):
            recompute(payload["subject_id"], payload["subject_side"])
        return
    if payload.get("talent_id"):
        recompute(payload["talent_id"], Side.TALENT)
    if payload.get("vendor_id"):
        recompute(payload["vendor_id"], Side.HOST)


def for_user(user_id, side: str) -> dict:
    """The stored reputation as the API shows it (empty before anything counts)."""
    return _shown(Reputation.objects.filter(user_id=user_id, side=side).first())


def for_user_object(user, side: str) -> dict:
    """Like for_user, from `user.reputations` (prefetch it and lists cost nothing)."""
    return _shown(next((r for r in user.reputations.all() if r.side == side), None))


def _shown(record) -> dict:
    if record is None:
        return {
            "rating_average": None,
            "review_count": 0,
            "completion_rate": None,
            "response_minutes": None,
            "badges": [],
        }
    return {
        "rating_average": record.rating_average,
        "review_count": record.review_count,
        "completion_rate": record.completion_rate,
        "response_minutes": record.response_minutes,
        "badges": record.badges,
    }


def recompute_all(now) -> dict[str, int]:
    """Job: everyone with a booking in the last year, both sides (catches badge rule
    changes and response times drifting out of the 90-day window), and their
    reliability scores with them."""
    since = now - timedelta(days=365)
    recent = Booking.objects.filter(status_changed_at__gte=since)
    count = 0
    from apps.reliability import services as reliability
    from apps.reliability.models import Side as ReliabilitySide

    for user_id in set(recent.values_list("talent_id", flat=True)):
        recompute(user_id, Side.TALENT, now=now)
        with transaction.atomic():
            reliability.recompute(user_id, ReliabilitySide.TALENT)
        count += 1
    for user_id in set(recent.values_list("vendor_id", flat=True)):
        recompute(user_id, Side.HOST, now=now)
        with transaction.atomic():
            reliability.recompute(user_id, ReliabilitySide.VENDOR)
        count += 1
    return {"recomputed": count}
