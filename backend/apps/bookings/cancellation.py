"""Calling a booking off before check-in, and offering the place to someone else.

cancel(): either side cancels a booking that is awaiting signatures or confirmed. They
pick a reason from REASONS_FOR their side (and say more for "other"). The cancellation
is recorded with its effect on the canceller's reliability, which the agreement's
cancellation policy decides (effect_for()):

- before both signed: no effect;
- earlier than the policy's notice period (3, 7 or 14 days): free;
- inside the notice period: late;
- a day or less before the stay starts: last minute.

A confirmed booking gives its slot back (the gig reopens if it was filled) and the place
is offered on (offer_place()): offers held when the gig filled open again first; if
nobody is then in line, the next shortlisted applicant gets an offer on the same terms
the host agreed before (settings.STEP_IN_OFFERS). The host still signs that agreement,
so nothing is binding on them until they do.
"""

from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.applications import services as applications
from apps.applications.constants import ApplicationStatus
from apps.applications.models import Application
from apps.bookings import confirmation
from apps.bookings.lifecycle import BEFORE_CHECK_IN, HOLDS_DATES, HOLDS_SLOT, Actor, BookingStatus
from apps.bookings.models import (
    REASONS_FOR,
    Booking,
    Cancellation,
    CancellationEffect,
    CancellationReason,
    CancelledBy,
)
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.gigs.models import Gig
from apps.offers.terms import CANCELLATION_NOTICE_DAYS

# A cancellation this many days or fewer before the stay is "last minute".
LAST_MINUTE_DAYS = 1


class CancellationRefused(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------- The policy (pure) ----------


@dataclass(frozen=True)
class Effect:
    effect: str
    policy: str
    notice_days: int | None
    days_before_start: int


def effect_for(*, by: str, was_status: str, policy: str, start: date, today: date) -> Effect:
    """What cancelling does to the canceller's reliability. Pure: no database."""
    days = (start - today).days
    notice = CANCELLATION_NOTICE_DAYS.get(policy)
    if by not in (CancelledBy.TALENT, CancelledBy.VENDOR) or was_status != BookingStatus.CONFIRMED:
        effect = CancellationEffect.NONE
    elif days <= LAST_MINUTE_DAYS:
        effect = CancellationEffect.LAST_MINUTE
    elif notice is not None and days < notice:
        effect = CancellationEffect.LATE
    else:
        effect = CancellationEffect.FREE
    return Effect(effect=effect, policy=policy, notice_days=notice, days_before_start=days)


def _policy(booking: Booking) -> str:
    """The cancellation policy of the version in force (or the one being signed)."""
    agreement = getattr(booking, "agreement", None)
    if agreement is None:
        return ""
    version = agreement.current_version or agreement.versions.order_by("number").first()
    return version.terms.get("cancellation_policy", "") if version else ""


def preview(booking: Booking, *, by: str, now=None) -> Effect:
    """What cancelling right now would do (shown before the person confirms)."""
    now = now or timezone.now()
    return effect_for(
        by=by,
        was_status=booking.status,
        policy=_policy(booking),
        start=booking.start_date,
        today=timezone.localdate(now),
    )


# ---------- Cancelling ----------


def _lock(booking_id):
    gig_id = Booking.objects.values_list("gig_id", flat=True).get(pk=booking_id)
    gig = Gig.objects.select_for_update().get(pk=gig_id)
    booking = (
        Booking.objects.select_for_update(of=("self",))
        .select_related("gig", "agreement__current_version")
        .get(pk=booking_id)
    )
    return gig, booking


def cancel(booking_id, *, user, by: str, reason: str, note: str = "", request=None, now=None):
    """Cancel before check-in, for one of the reasons `by` may give."""
    now = now or timezone.now()
    note = note.strip()
    if reason not in REASONS_FOR.get(by, ()):
        allowed = ", ".join(REASONS_FOR.get(by, ()))
        raise CancellationRefused(f"Pick one of the reasons: {allowed}.", 400)
    if reason == CancellationReason.OTHER and not note:
        raise CancellationRefused("Say a little about why.", 400)
    with transaction.atomic():
        _, booking = _lock(booking_id)
        if booking.status not in BEFORE_CHECK_IN:
            raise CancellationRefused(
                f"The booking is {booking.get_status_display().lower()}: only a booking that "
                "hasn't checked in yet can be cancelled here."
            )
        booking = _cancel_locked(
            booking, user=user, by=by, reason=reason, note=note, request=request, now=now
        )
    return booking


def cancel_by_system(booking: Booking, *, reason: str, now) -> Booking:
    """Called with the gig and booking locked (confirmation.settle_others, jobs)."""
    return _cancel_locked(booking, user=None, by=CancelledBy.SYSTEM, reason=reason, now=now)


def _cancel_locked(booking, *, user, by, reason, note="", request=None, now) -> Booking:
    from apps.bookings import services as bookings

    was_status = booking.status
    effect = preview(booking, by=by, now=now)
    Cancellation.objects.create(
        booking=booking,
        by=by,
        user=user if getattr(user, "is_authenticated", False) else None,
        reason=reason,
        note=note,
        was_status=was_status,
        policy=effect.policy,
        notice_days=effect.notice_days,
        days_before_start=effect.days_before_start,
        effect=effect.effect,
        created_at=now,
    )
    label = CancellationReason(reason).label
    try:
        booking = bookings.transition(
            booking.pk,
            BookingStatus.CANCELLED,
            actor=by,
            user=user,
            reason=f"{label}. {note}".strip() if note else label,
            metadata={
                "reason_code": reason,
                "effect": effect.effect,
                "policy": effect.policy,
                "days_before_start": effect.days_before_start,
            },
            request=request,
            now=now,
        )
    except bookings.BookingRefused as exc:
        raise CancellationRefused(str(exc)) from exc
    if was_status in HOLDS_SLOT:
        offer_place(booking, now=now)
    return booking


def cancel_unsigned(now) -> dict[str, int]:
    """Job: bookings still awaiting signatures when the stay starts are called off."""
    due = Booking.objects.filter(
        status=BookingStatus.SIGNING, start_date__lte=timezone.localdate(now)
    ).values_list("pk", flat=True)
    cancelled = 0
    for pk in list(due):
        with transaction.atomic():
            _, booking = _lock(pk)
            if booking.status != BookingStatus.SIGNING:
                continue
            cancel_by_system(booking, reason=CancellationReason.NOT_SIGNED, now=now)
            cancelled += 1
    return {"unsigned_cancelled": cancelled}


# ---------- Offering the place on ----------


def offer_place(vacated: Booking, *, now) -> dict[str, int]:
    """A slot came free: reopen held offers, then offer it to the next shortlisted
    applicant if nobody is in line. The gig is locked by the caller."""
    from apps.offers.models import Offer, OfferStatus

    gig = Gig.objects.get(pk=vacated.gig_id)
    free = gig.slots - confirmation.taken_slots(gig.pk)
    result = {"reopened": 0, "step_in": 0}
    if free <= 0:
        return result
    in_line = (
        Booking.objects.filter(gig=gig, status=BookingStatus.SIGNING).count()
        + Offer.objects.filter(application__gig=gig, status=OfferStatus.OPEN).count()
    )
    held = (
        Offer.objects.select_for_update()
        .select_related("application__gig")
        .filter(application__gig=gig, status=OfferStatus.HELD)
        .order_by("created_at")
    )
    for offer in held[: max(free - in_line, 0)]:
        reopen_offer(offer, now=now)
        result["reopened"] += 1
        in_line += 1
    if in_line > 0:
        _announce(vacated, now=now, step_in=None)
        return result
    if getattr(settings, "STEP_IN_OFFERS", True) and (offer := step_in_offer(vacated, now=now)):
        result["step_in"] = 1
        _announce(vacated, now=now, step_in=offer)
    else:
        _announce(vacated, now=now, step_in=None)
    return result


def reopen_offer(offer, *, now) -> None:
    from apps.bookings.lifecycle import OFFER_TTL
    from apps.offers.models import OfferStatus

    application = offer.application
    offer.status = OfferStatus.OPEN
    offer.status_reason = "A place opened up."
    offer.save(update_fields=["status", "status_reason"])
    application.offer_expires_at = now + OFFER_TTL
    application.save(update_fields=["offer_expires_at", "updated_at"])
    log_action(
        actor=None,
        action="offer.reopened",
        obj=offer,
        before={"status": OfferStatus.HELD},
        after={"status": OfferStatus.OPEN, "offer_expires_at": application.offer_expires_at},
    )
    publish(
        DomainEvent(
            "offer.reopened",
            {
                "offer_id": str(offer.pk),
                "application_id": str(application.pk),
                "gig_id": str(application.gig_id),
                "gig_title": application.gig.title,
                "talent_id": str(application.talent_id),
                "vendor_id": str(application.gig.vendor_id),
                "by": Actor.SYSTEM,
                "offer_expires_at": application.offer_expires_at,
            },
            occurred_at=now,
        )
    )


def _step_in_terms(vacated: Booking) -> dict | None:
    agreement = getattr(vacated, "agreement", None)
    if agreement is None:
        return None
    version = agreement.current_version or agreement.versions.order_by("-number").first()
    return dict(version.terms) if version else None


def step_in_offer(vacated: Booking, *, now):
    """Offer the vacated place to the best-fitting shortlisted applicant who is free on
    those dates, on the terms the host agreed for it. None if there's nobody, or the
    stay has already started."""
    from apps.offers import services as offers
    from apps.offers import terms as offer_terms
    from apps.offers.models import Party

    terms = _step_in_terms(vacated)
    if terms is None:
        return None
    gig = vacated.gig
    try:
        frozen = offer_terms.validate(
            terms, compensation_model=gig.compensation_model, today=timezone.localdate(now)
        )
    except Exception:  # the dates are past, or the terms no longer validate
        return None
    start, end = date.fromisoformat(frozen["start_date"]), date.fromisoformat(frozen["end_date"])
    busy = Booking.objects.filter(
        status__in=HOLDS_DATES, start_date__lt=end, end_date__gt=start
    ).values("talent_id")
    candidates = (
        Application.objects.filter(gig=gig, status=ApplicationStatus.SHORTLISTED)
        .exclude(talent_id__in=busy)
        .exclude(offers__isnull=False)
        .order_by("-fit_score", "applied_at")
    )
    application_id = candidates.values_list("pk", flat=True).first()
    if application_id is None:
        return None
    application = applications.lock(application_id)
    applications.move(
        application,
        ApplicationStatus.OFFERED,
        actor=Actor.SYSTEM,
        reason="A place opened up.",
        now=now,
    )
    return offers.create_step_in(
        application, terms=frozen, vacated=vacated, by=Party.VENDOR, now=now
    )


def _announce(vacated: Booking, *, now, step_in) -> None:
    publish(
        DomainEvent(
            "booking.place_opened",
            {
                "booking_id": str(vacated.pk),
                "gig_id": str(vacated.gig_id),
                "gig_title": vacated.gig.title,
                "vendor_id": str(vacated.vendor_id),
                "talent_id": str(vacated.talent_id),
                "step_in_application_id": str(step_in.application_id) if step_in else "",
                "by": Actor.SYSTEM,
            },
            occurred_at=now,
        )
    )
