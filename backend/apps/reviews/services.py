"""Reviews after a completed booking: one per side, double-blind.

- Either side may review from completion until REVIEW_WINDOW_DAYS (14) later.
- Both reviews stay hidden until both are in, then publish together; or, when the
  window closes, whatever was submitted publishes (close_windows job).
- A review with flagged words or contact details is held for a moderator, and its pair
  waits for the decision, so they still publish together.
- Published reviews can't be edited (a database trigger enforces it). The reviewed
  person may reply once. Anyone may report a review; reports queue it for a moderator,
  who allows or removes it.
"""

import contextlib
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.models import Booking
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.reviews.models import (
    Reply,
    Review,
    ReviewReport,
    ReviewStatus,
    Side,
)
from apps.reviews.moderation import flags_for

S = ReviewStatus
REVIEWABLE = (BookingStatus.COMPLETED, BookingStatus.REVIEWED)
CATEGORIES = ("communication", "accuracy", "safety", "reliability")
CATEGORY_LABELS = {
    Side.HOST: {
        "communication": "Communication",
        "accuracy": "Accuracy of the listing",
        "safety": "Safety",
        "reliability": "Payment as agreed",
    },
    Side.TALENT: {
        "communication": "Communication",
        "accuracy": "Quality of the work",
        "safety": "Safety",
        "reliability": "Punctuality",
    },
}


class ReviewError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def window_closes(booking: Booking):
    done = booking.completed_at or booking.status_changed_at
    return done + timedelta(days=settings.REVIEW_WINDOW_DAYS)


def side_of(booking: Booking, user) -> str | None:
    """The side `user` reviews (the other party's): host for the talent, and so on."""
    if booking.talent_id == user.pk:
        return Side.HOST
    if booking.vendor_id == user.pk:
        return Side.TALENT
    return None


def _event(name: str, review: Review, now, *, notify: list[str], key: str, **extra) -> None:
    booking = review.booking
    publish(
        DomainEvent(
            name,
            {
                "booking_id": str(booking.pk),
                "review_id": str(review.pk),
                "gig_title": booking.gig.title,
                "talent_id": str(booking.talent_id),
                "vendor_id": str(booking.vendor_id),
                "subject_id": str(review.subject_id),
                "subject_side": review.subject_side,
                "dedup_key": f"{name}:{review.pk}:{key}",
                "notify": notify,
                **extra,
            },
            occurred_at=now,
        )
    )


def _side_label(side: str) -> str:
    return "talent" if side == Side.TALENT else "vendor"


# ---------- Writing ----------


def submit(
    booking_id, *, author, rating: int, text: str, request=None, now=None, **categories
) -> Review:
    now = now or timezone.now()
    text = text.strip()
    if len(text) < settings.REVIEW_MIN_LENGTH:
        raise ReviewError(
            f"Write at least {settings.REVIEW_MIN_LENGTH} characters about your stay.", 400
        )
    with transaction.atomic():
        booking = (
            Booking.objects.select_for_update(of=("self",))
            .select_related("gig")
            .filter(pk=booking_id)
            .first()
        )
        side = booking and side_of(booking, author)
        if side is None:
            raise Booking.DoesNotExist
        if booking.status not in REVIEWABLE:
            raise ReviewError("You can review once the stay is completed.")
        if now >= window_closes(booking):
            raise ReviewError("The time to review this stay has passed.")
        flags = flags_for(text)
        try:
            with transaction.atomic():
                review = Review.objects.create(
                    booking=booking,
                    author=author,
                    subject_id=booking.vendor_id if side == Side.HOST else booking.talent_id,
                    subject_side=side,
                    rating=rating,
                    text=text,
                    flags=flags,
                    held_until_cleared=bool(flags),
                    status=S.HELD if flags else S.SUBMITTED,
                    submitted_at=now,
                    **{c: categories[c] for c in CATEGORIES},
                )
        except IntegrityError as exc:
            raise ReviewError("You've already reviewed this stay.") from exc
        log_action(
            actor=author,
            action="reviews.submitted",
            obj=review,
            after={"rating": rating, "flags": flags},
            request=request,
        )
        other = "vendor" if side == Side.HOST else "talent"
        if not booking.reviews.exclude(pk=review.pk).exists():
            # Nudge the other side; what was written stays hidden.
            _event("reviews.awaiting_yours", review, now, notify=[other], key="nudge")
        _publish_if_ready(booking, now)
    return review


def _publish_if_ready(booking: Booking, now, *, window_closed: bool = False) -> list[Review]:
    """Both in and none held: publish both. Window closed: publish what isn't held."""
    reviews = list(booking.reviews.select_for_update().select_related("booking__gig"))
    waiting = [r for r in reviews if r.status == S.SUBMITTED]
    held = any(r.status == S.HELD for r in reviews)
    both_in = len(reviews) == 2
    if not waiting or (not window_closed and (not both_in or held)):
        return []
    for review in waiting:
        review.status, review.published_at = S.PUBLISHED, now
        review.save(update_fields=["status", "published_at"])
        log_action(
            actor=None,
            action="reviews.published",
            obj=review,
            after={"rating": review.rating, "window_closed": window_closed},
        )
        _event(
            "reviews.published",
            review,
            now,
            notify=[_side_label(review.subject_side)],
            key="published",
        )
    _mark_booking_reviewed(booking, now)
    return waiting


def _mark_booking_reviewed(booking: Booking, now) -> None:
    from apps.bookings.services import BookingRefused, transition

    booking.refresh_from_db(fields=["status"])
    if booking.status == BookingStatus.COMPLETED:
        # Refused if, say, it was disputed meanwhile: the reviews still stand.
        with contextlib.suppress(BookingRefused):
            transition(
                booking.pk,
                BookingStatus.REVIEWED,
                actor=Actor.SYSTEM,
                now=now,
                reason="Reviews published",
            )


def close_windows(now) -> dict[str, int]:
    """Job: publish what was submitted for stays whose window has closed; remind
    whoever hasn't reviewed two days before it does."""
    days = settings.REVIEW_WINDOW_DAYS
    published = reminded = 0
    candidates = Booking.objects.filter(
        status__in=REVIEWABLE, completed_at__isnull=False, reviews__status=S.SUBMITTED
    ).distinct()
    for booking in candidates.filter(completed_at__lte=now - timedelta(days=days)):
        with transaction.atomic():
            locked = Booking.objects.select_for_update(of=("self",)).get(pk=booking.pk)
            published += len(_publish_if_ready(locked, now, window_closed=True))
    soon = Booking.objects.filter(
        status=BookingStatus.COMPLETED,
        completed_at__lte=now - timedelta(days=days - 2),
        completed_at__gt=now - timedelta(days=days),
    ).select_related("gig")
    for booking in soon:
        authors = set(booking.reviews.values_list("author_id", flat=True))
        for side, user_id in (("talent", booking.talent_id), ("vendor", booking.vendor_id)):
            if user_id in authors:
                continue
            publish(
                DomainEvent(
                    "reviews.window_closing",
                    {
                        "booking_id": str(booking.pk),
                        "gig_title": booking.gig.title,
                        "talent_id": str(booking.talent_id),
                        "vendor_id": str(booking.vendor_id),
                        "dedup_key": f"reviews.window_closing:{booking.pk}",
                        "notify": [side],
                    },
                    occurred_at=now,
                )
            )
            reminded += 1
    return {"published": published, "reminded": reminded}


# ---------- Replies and reports ----------


def reply(review_id, *, user, text: str, request=None, now=None) -> Reply:
    now = now or timezone.now()
    text = text.strip()
    if not text:
        raise ReviewError("Write your reply.", 400)
    with transaction.atomic():
        review = Review.objects.select_for_update().get(pk=review_id, subject=user)
        if review.status != S.PUBLISHED:
            raise ReviewError("You can reply once the review is published.")
        if hasattr(review, "reply"):
            raise ReviewError("You've already replied to this review.")
        flags = flags_for(text)
        answer = Reply.objects.create(
            review=review,
            text=text[:1000],
            flags=flags,
            status=S.HELD if flags else S.PUBLISHED,
            created_at=now,
        )
        log_action(
            actor=user,
            action="reviews.replied",
            obj=review,
            after={"flags": flags},
            request=request,
        )
    return answer


def report(review_id, *, user, reason: str, note: str = "", request=None, now=None):
    now = now or timezone.now()
    review = Review.objects.filter(pk=review_id, status=S.PUBLISHED).first()
    if review is None:
        raise Review.DoesNotExist
    try:
        with transaction.atomic():
            entry = ReviewReport.objects.create(
                review=review, reporter=user, reason=reason, note=note.strip()[:500], created_at=now
            )
    except IntegrityError as exc:
        raise ReviewError("You've already reported this review.") from exc
    log_action(
        actor=user, action="reviews.reported", obj=review, after={"reason": reason}, request=request
    )
    return entry


# ---------- Moderation ----------


def moderate(review_id, *, admin, decision: str, note: str, request=None, now=None) -> Review:
    """Allow (a held review goes on to publish as usual; reports are cleared) or remove
    (it never shows, or stops showing, and doesn't count)."""
    now = now or timezone.now()
    if decision not in ("allow", "remove"):
        raise ReviewError("Decide allow or remove.", 400)
    if not note.strip():
        raise ReviewError("Say why.", 400)
    with transaction.atomic():
        review = Review.objects.select_for_update().select_related("booking__gig").get(pk=review_id)
        if review.status == S.REMOVED:
            raise ReviewError("This review was removed already.")
        before = {"status": review.status}
        review.moderated_by, review.moderated_at = admin, now
        review.moderation_note = note.strip()[:300]
        if decision == "remove":
            review.status = S.REMOVED
        elif review.status == S.HELD:
            review.status = S.SUBMITTED
        review.save()
        ReviewReport.objects.filter(review=review, resolved_at__isnull=True).update(resolved_at=now)
        log_action(
            actor=admin,
            action=f"reviews.moderated_{decision}",
            obj=review,
            before=before,
            after={"status": review.status, "note": note},
            request=request,
        )
        if decision == "remove":
            _event("reviews.removed", review, now, notify=[], key="removed")
        booking = Booking.objects.select_for_update(of=("self",)).get(pk=review.booking_id)
        _publish_if_ready(booking, now, window_closed=now >= window_closes(booking))
        # The pair may have been waiting only for this one.
        if decision == "remove":
            _publish_if_ready(booking, now, window_closed=True)
    return review


def moderate_reply(reply_id, *, admin, decision: str, note: str, now=None) -> Reply:
    if decision not in ("allow", "remove") or not note.strip():
        raise ReviewError("Decide allow or remove, and say why.", 400)
    answer = Reply.objects.get(pk=reply_id)
    answer.status = S.PUBLISHED if decision == "allow" else S.REMOVED
    answer.save(update_fields=["status"])
    log_action(
        actor=admin, action=f"reviews.reply_{decision}", obj=answer.review, after={"note": note}
    )
    return answer
