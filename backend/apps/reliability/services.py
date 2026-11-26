"""Counting what someone did, and keeping their stored reliability score current.

What counts, for one person on one side (docs/reliability.md):

- completed: their bookings on that side that reached completed (or reviewed);
- on_time_replies: offers sent to them that they answered (accepted, declined or
  countered) before the offer lapsed. The talent answers the host's offers; the host
  answers the talent's counters. Offers that lapse earn nothing;
- late / last-minute cancellations: bookings they cancelled once confirmed, inside the
  agreement's notice period (apps.bookings.cancellation.effect_for);
- no-shows: their bookings as talent marked no-show (and not overturned on dispute);
- good / poor reviews: published reviews of them on that side with 4-5 / 1-2 stars
  (apps.reviews). Removed reviews don't count.
"""

from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking, Cancellation, CancellationEffect
from apps.common.events import DomainEvent
from apps.common.services.audit import log_action
from apps.offers.models import Offer, OfferStatus, Party
from apps.reliability.models import ReliabilityScore, Side
from apps.reliability.score import Inputs, Reliability, score

COMPLETED = (BookingStatus.COMPLETED, BookingStatus.REVIEWED)
ANSWERED = (OfferStatus.ACCEPTED, OfferStatus.DECLINED, OfferStatus.COUNTERED)

# Events after which someone's counts may have changed.
RECOMPUTE_ON = (
    "booking.completed",
    "booking.reviewed",
    "booking.no_show",
    "booking.disputed",
    "booking.cancelled",
    "application.confirmed",
    "application.declined",
    "offer.countered",
    "offer.counter_declined",
    "reviews.published",
    "reviews.removed",
)


def inputs_for(user_id, side: str) -> Inputs:
    if side == Side.TALENT:
        bookings = Booking.objects.filter(talent_id=user_id)
        replies = Offer.objects.filter(
            application__talent_id=user_id, proposed_by=Party.VENDOR, status__in=ANSWERED
        )
        no_shows = bookings.filter(status=BookingStatus.NO_SHOW).count()
    else:
        bookings = Booking.objects.filter(vendor_id=user_id)
        replies = Offer.objects.filter(
            application__gig__vendor_id=user_id, proposed_by=Party.TALENT, status__in=ANSWERED
        )
        no_shows = 0  # v1 has no way to mark a host as a no-show
    cancellations = Cancellation.objects.filter(
        booking__in=bookings,
        by=side,
        effect__in=(CancellationEffect.LATE, CancellationEffect.LAST_MINUTE),
    )
    from apps.reviews.models import Review, ReviewStatus
    from apps.reviews.models import Side as ReviewSide

    reviews = Review.objects.filter(
        subject_id=user_id,
        subject_side=ReviewSide.TALENT if side == Side.TALENT else ReviewSide.HOST,
        status=ReviewStatus.PUBLISHED,
    )
    return Inputs(
        good_reviews=reviews.filter(rating__gte=4).count(),
        poor_reviews=reviews.filter(rating__lte=2).count(),
        completed=bookings.filter(status__in=COMPLETED).count(),
        on_time_replies=replies.count(),
        late_cancellations=cancellations.filter(effect=CancellationEffect.LATE).count(),
        last_minute_cancellations=cancellations.filter(
            effect=CancellationEffect.LAST_MINUTE
        ).count(),
        no_shows=no_shows,
    )


def recompute(user_id, side: str) -> ReliabilityScore:
    inputs = inputs_for(user_id, side)
    result = score(inputs)
    record, _ = ReliabilityScore.objects.select_for_update().get_or_create(
        user_id=user_id, side=side
    )
    before = {"score": record.score, "level": record.level}
    record.score, record.level, record.version = result.score, result.level, result.version
    record.inputs = inputs.__dict__.copy()
    record.breakdown = result.breakdown
    record.save()
    if before != {"score": record.score, "level": record.level}:
        log_action(
            actor=None,
            action="reliability.changed",
            obj=record,
            before=before,
            after={"score": record.score, "level": record.level, "inputs": record.inputs},
        )
    return record


def on_event(event: DomainEvent) -> None:
    """Recompute both people's scores on the side each was on."""
    for side, key in ((Side.TALENT, "talent_id"), (Side.VENDOR, "vendor_id")):
        if user_id := event.payload.get(key):
            recompute(user_id, side)


def neutral() -> Reliability:
    return score(Inputs())


def for_user(user, side: str) -> dict:
    """The stored score as the API shows it (neutral until something counts). Uses
    `user.reliability_scores` so a prefetch makes lists free."""
    record = next((r for r in user.reliability_scores.all() if r.side == side), None)
    if record is None:
        result = neutral()
        return {"score": result.score, "level": result.level, "version": result.version}
    return {"score": record.score, "level": record.level, "version": record.version}
