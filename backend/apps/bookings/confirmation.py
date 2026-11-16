"""What happens when both sides have signed: the booking is confirmed.

agreements.services.sign() calls confirm_signed() inside its transaction, with the gig,
booking, agreement and version locked, as soon as version 1 has both signatures:

1. The booking moves signing → confirmed (the transition table checks a slot is still
   free) and takes one of the gig's slots.
2. The gig is marked filled when its slots are full (gigs.services, via _sync_slots).
3. If the gig is now full, the other offers for it are held or expired, as
   settings.BOOKING_WHEN_FULL says:
   - "hold": open offers go on hold until a place opens (they lapse when the stay would
     have started), and other bookings still being signed wait: they can't be signed
     until a place opens.
   - "expire": open offers lapse (their applications expire) and other bookings still
     being signed are cancelled, with no effect on anyone's reliability.
4. Both sides can now see the unlocked details (see unlocked_details()).

Locks: the gig row is already locked by the caller, so taking application and offer
locks after the agreement's cannot deadlock: everything touching this gig queues on it.
"""

from dataclasses import dataclass
from datetime import datetime, time

from django.conf import settings
from django.utils import timezone

from apps.applications import services as applications
from apps.applications.constants import ApplicationStatus
from apps.bookings.lifecycle import HOLDS_SLOT, Actor, BookingStatus
from apps.bookings.models import Booking
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action, snapshot

HOLD, EXPIRE = "hold", "expire"
WHEN_FULL_RULES = (HOLD, EXPIRE)


class ConfirmationRefused(Exception):
    """Both signed, but the booking can't be confirmed (every slot was taken meanwhile)."""


def when_full_rule() -> str:
    rule = getattr(settings, "BOOKING_WHEN_FULL", HOLD)
    if rule not in WHEN_FULL_RULES:
        raise ValueError(f"BOOKING_WHEN_FULL must be one of {WHEN_FULL_RULES}, not {rule!r}.")
    return rule


def taken_slots(gig_id) -> int:
    return Booking.objects.filter(gig_id=gig_id, status__in=HOLDS_SLOT).count()


def confirm_signed(booking: Booking, *, version_number: int, now) -> Booking:
    """Both sides signed: confirm the booking, take the slot, settle the other offers.
    Does nothing for a booking already confirmed (a later version signed)."""
    from apps.bookings import services as bookings

    if booking.status != BookingStatus.SIGNING:
        return booking
    try:
        booking = bookings.transition(
            booking.pk,
            BookingStatus.CONFIRMED,
            actor=Actor.SYSTEM,
            reason=f"Both sides signed version {version_number} of the agreement.",
            metadata={"agreement_version": version_number},
            now=now,
        )
    except bookings.BookingRefused as exc:
        raise ConfirmationRefused(
            "Every place on this gig was taken before you both signed. If one opens up, "
            "you'll be able to sign then."
        ) from exc
    if taken_slots(booking.gig_id) >= booking.gig.slots:
        settle_others(booking, now=now)
    return booking


def _hold_until(offer) -> datetime:
    """A held offer lapses when the stay it offers would have started."""
    start = datetime.fromisoformat(offer.terms["start_date"]).date()
    return timezone.make_aware(datetime.combine(start, time.min))


def settle_others(confirmed: Booking, *, now) -> dict[str, int]:
    """The gig is full: hold or expire the other open offers and unsigned bookings."""
    from apps.bookings import cancellation
    from apps.offers.models import Offer, OfferStatus

    rule = when_full_rule()
    gig = confirmed.gig
    counts = {"held": 0, "expired": 0, "waiting": 0, "cancelled": 0}
    offers = (
        Offer.objects.select_for_update()
        .select_related("application__gig", "application__talent")
        .filter(application__gig_id=gig.pk, status=OfferStatus.OPEN)
        .exclude(application_id=confirmed.application_id)
        .order_by("created_at")
    )
    for offer in offers:
        application = offer.application
        if rule == HOLD:
            hold_offer(offer, application, now=now)
            counts["held"] += 1
        else:
            applications.move(
                application,
                ApplicationStatus.EXPIRED,
                actor=Actor.SYSTEM,
                reason="Every place on this gig has been filled.",
                now=now,
            )
            counts["expired"] += 1
    signing = (
        Booking.objects.select_for_update()
        .select_related("gig")
        .filter(gig_id=gig.pk, status=BookingStatus.SIGNING)
        .exclude(pk=confirmed.pk)
    )
    for other in signing:
        if rule == HOLD:
            publish(
                DomainEvent(
                    "booking.waiting_for_place",
                    {**_payload(other), "by": Actor.SYSTEM},
                    occurred_at=now,
                )
            )
            counts["waiting"] += 1
        else:
            cancellation.cancel_by_system(
                other, reason=cancellation.CancellationReason.SLOTS_FILLED, now=now
            )
            counts["cancelled"] += 1
    log_action(
        actor=None,
        action="gig.full_settled",
        obj=gig,
        after={"rule": rule, "booking_id": str(confirmed.pk), **counts},
    )
    return counts


def hold_offer(offer, application, *, now) -> None:
    from apps.offers.models import OfferStatus

    before = snapshot(offer, ["status", "status_reason"])
    offer.status = OfferStatus.HELD
    offer.status_reason = (
        "Every place is taken for now. If one opens up before the stay, this offer opens again."
    )
    offer.save(update_fields=["status", "status_reason"])
    app_before = snapshot(application, ["offer_expires_at"])
    application.offer_expires_at = _hold_until(offer)
    application.save(update_fields=["offer_expires_at", "updated_at"])
    log_action(
        actor=None,
        action="offer.held",
        obj=offer,
        before={**before, **app_before},
        after={**snapshot(offer, ["status"]), **snapshot(application, ["offer_expires_at"])},
    )
    publish(
        DomainEvent(
            "offer.held",
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


def _payload(booking: Booking) -> dict:
    return {
        "booking_id": str(booking.pk),
        "gig_id": str(booking.gig_id),
        "gig_title": booking.gig.title,
        "talent_id": str(booking.talent_id),
        "vendor_id": str(booking.vendor_id),
    }


# ---------- Unlocked details ----------


@dataclass(frozen=True)
class Contact:
    name: str
    phone: str


@dataclass(frozen=True)
class Place:
    name: str
    address: str
    city: str
    state: str
    pincode: str
    latitude: float | None
    longitude: float | None
    directions: str

    @property
    def maps_url(self) -> str:
        if self.latitude is None or self.longitude is None:
            return ""
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&destination={self.latitude:.6f},{self.longitude:.6f}"
        )


@dataclass(frozen=True)
class Unlocked:
    booking_id: str
    status: str
    host: Contact
    talent: Contact
    place: Place | None  # the talent's to see; the host knows it


# Details stay unlocked from confirmation until the stay ends or is called off (the same
# rule as the property's exact location: apps.properties.services.can_see_exact_location).
UNLOCKED_WHILE = frozenset(
    {BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.DELIVERING}
)


def unlocked_details(booking: Booking, *, party: str) -> Unlocked | None:
    """What a confirmed booking unlocks: the exact address and directions for the
    talent, and each side's verified phone (the one they sign in with by OTP).
    None before confirmation or once the booking is over."""
    if booking.status not in UNLOCKED_WHILE:
        return None
    from apps.profiles.models import TalentProfile, VendorProfile

    vendor_profile = VendorProfile.objects.filter(user_id=booking.vendor_id).first()
    talent_profile = TalentProfile.objects.filter(user_id=booking.talent_id).first()
    host = Contact(
        name=(vendor_profile.contact_name or str(vendor_profile)) if vendor_profile else "Host",
        phone=booking.vendor.phone,
    )
    talent = Contact(
        name=str(talent_profile) if talent_profile else "Talent", phone=booking.talent.phone
    )
    place = None
    if party == Actor.TALENT:
        prop = booking.gig.property
        place = Place(
            name=prop.name,
            address=prop.address,
            city=prop.city,
            state=prop.state,
            pincode=prop.pincode,
            latitude=float(prop.latitude) if prop.latitude is not None else None,
            longitude=float(prop.longitude) if prop.longitude is not None else None,
            directions=prop.directions,
        )
    return Unlocked(
        booking_id=str(booking.pk), status=booking.status, host=host, talent=talent, place=place
    )
