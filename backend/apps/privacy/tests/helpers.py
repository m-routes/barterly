from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.tests.helpers import booked
from apps.chat import services as chat
from apps.notifications.models import PushDevice
from apps.privacy.services import consents

V = "2026-11-draft-1"


def finished_booking():
    """A booking both sides signed, then completed: nothing blocks deletion."""
    booking = booked()
    Booking.objects.filter(pk=booking.pk).update(status="completed")
    booking.refresh_from_db()
    return booking


def busy_talent():
    """Talent with a profile, consents, a device, a signed agreement and a chat."""
    booking = finished_booking()
    talent = booking.talent
    consents.record_sign_up(talent, terms_version=V, privacy_version=V, source="mobile")
    consents.record(talent, "location", granted=True, version=V)
    PushDevice.objects.create(user=talent, token=f"tok-{talent.pk}", platform="android")
    conversation = chat.vendor_open(booking.application_id, vendor=booking.vendor)
    chat.send(conversation.pk, sender=talent, body="See you on the 3rd!", client_id="c1")
    return booking, talent, timezone.now()
