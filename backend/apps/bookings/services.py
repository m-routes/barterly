"""Accepting offers and moving bookings, as the one transition table allows.

Locks are always taken gig first, then the application or booking, so two requests
for the same gig queue up instead of deadlocking, and slot counts are read while the
gig row is locked (two simultaneous confirmations of the last slot can't both win).
"""

from django.db import transaction
from django.utils import timezone

from apps.applications import services as applications
from apps.applications.constants import ApplicationStatus
from apps.bookings import lifecycle
from apps.bookings.lifecycle import HOLDS_SLOT, Actor, BookingStatus
from apps.bookings.models import Booking, BookingEvent
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action, snapshot
from apps.gigs.models import Gig
from apps.gigs.services import on_confirmed_bookings_changed

AUDIT_FIELDS = ["status", "status_reason"]
STATUS_TIMESTAMPS = {
    BookingStatus.CHECKED_IN: "checked_in_at",
    BookingStatus.COMPLETED: "completed_at",
    BookingStatus.CANCELLED: "cancelled_at",
}


class BookingRefused(Exception):
    """The transition table doesn't allow this (the message says why)."""


def actor_for(user, booking: Booking) -> str | None:
    if booking.talent_id == user.pk:
        return Actor.TALENT
    if booking.vendor_id == user.pk:
        return Actor.VENDOR
    if getattr(user, "is_admin_role", False):
        return Actor.ADMIN
    return None


def _event_payload(booking: Booking, frm: str, actor: str, reason: str) -> dict:
    return {
        "booking_id": str(booking.pk),
        "application_id": str(booking.application_id),
        "gig_id": str(booking.gig_id),
        "gig_title": booking.gig.title,
        "talent_id": str(booking.talent_id),
        "vendor_id": str(booking.vendor_id),
        "from": frm,
        "to": booking.status,
        "by": actor,
        "reason": reason,
        "start_date": booking.start_date,
        "end_date": booking.end_date,
    }


def _record(booking, frm, *, actor, user, reason, metadata, request, now, before) -> None:
    BookingEvent.objects.create(
        booking=booking,
        from_state=frm,
        to_state=booking.status,
        actor=actor,
        actor_user=user if getattr(user, "is_authenticated", False) else None,
        reason=reason,
        metadata=metadata or {},
        created_at=now,
    )
    log_action(
        actor=user,
        action=f"booking.{booking.status}",
        obj=booking,
        before=before,
        after={**snapshot(booking, AUDIT_FIELDS), "by": actor},
        request=request,
    )
    publish(
        DomainEvent(
            f"booking.{booking.status}",
            _event_payload(booking, frm, actor, reason),
            occurred_at=now,
        )
    )


def _sync_slots(gig_id) -> None:
    taken = Booking.objects.filter(gig_id=gig_id, status__in=HOLDS_SLOT).count()
    on_confirmed_bookings_changed(gig_id, taken)


def accept_offer(application_id, *, talent, request=None, now=None) -> Booking:
    """The talent accepts an offer: offered → confirmed, and the booking is created.

    The gig row stays locked from the slot check to the insert, so the last slot goes
    to exactly one of two people accepting at the same moment.
    """
    now = now or timezone.now()
    with transaction.atomic():
        application = applications.lock(application_id)
        if application.talent_id != talent.pk:
            raise Booking.DoesNotExist
        try:
            applications.move(
                application,
                ApplicationStatus.CONFIRMED,
                actor=Actor.TALENT,
                user=talent,
                request=request,
                now=now,
            )
        except applications.InvalidApplicationTransition as exc:
            raise BookingRefused(str(exc)) from exc
        booking = Booking.objects.create(
            application=application,
            gig=application.gig,
            talent=application.talent,
            vendor=application.gig.vendor,
            start_date=application.proposed_start,
            end_date=application.proposed_end,
            confirmed_at=now,
            status_changed_at=now,
        )
        _record(
            booking,
            ApplicationStatus.OFFERED,
            actor=Actor.TALENT,
            user=talent,
            reason="",
            metadata={"offer_expires_at": application.offer_expires_at},
            request=request,
            now=now,
            before={"status": ApplicationStatus.OFFERED},
        )
        _sync_slots(booking.gig_id)
    return booking


def transition(
    booking_id,
    to: str,
    *,
    actor: str,
    user=None,
    reason: str = "",
    metadata: dict | None = None,
    request=None,
    now=None,
) -> Booking:
    """Move a booking as the transition table allows. Writes a BookingEvent and an
    AuditLog row and publishes booking.<status>, all in one transaction."""
    now = now or timezone.now()
    reason = reason.strip()
    with transaction.atomic():
        gig_id = Booking.objects.values_list("gig_id", flat=True).get(pk=booking_id)
        Gig.objects.select_for_update().get(pk=gig_id)
        booking = Booking.objects.select_for_update().select_related("gig").get(pk=booking_id)
        ctx = lifecycle.Context(subject=booking, actor=actor, reason=reason, now=now)
        try:
            lifecycle.check(booking.status, to, ctx)
        except (lifecycle.InvalidTransition, lifecycle.GuardFailed) as exc:
            raise BookingRefused(str(exc)) from exc
        frm = booking.status
        before = snapshot(booking, AUDIT_FIELDS)
        booking.status = to
        booking.status_reason = reason
        booking.status_changed_at = now
        if field := STATUS_TIMESTAMPS.get(to):
            setattr(booking, field, now)
        booking.save()
        _record(
            booking,
            frm,
            actor=actor,
            user=user,
            reason=reason,
            metadata=metadata,
            request=request,
            now=now,
            before=before,
        )
        if (frm in HOLDS_SLOT) != (to in HOLDS_SLOT):
            _sync_slots(gig_id)
    return booking
