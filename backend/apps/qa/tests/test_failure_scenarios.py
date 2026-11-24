"""Failure scenarios, end to end through the services (docs/qa/README.md lists them all).

Each scenario is something that goes wrong for a real person, played through from their
side to the outcome they should see. Narrower unit tests live with each app.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.fakes import UNAVAILABLE
from apps.attendance import services as attendance
from apps.bookings.cancellation import CancelledBy, cancel, preview
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.models import Booking
from apps.bookings.services import transition
from apps.money import escrow
from apps.money.models import Escrow, LedgerTransaction
from apps.money.tests.helpers import capture, ensure_accounts, paid_booking

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _accounts():
    ensure_accounts()


def at_start(booking, hour=10):
    from datetime import datetime, time

    return timezone.make_aware(datetime.combine(booking.start_date, time(hour)))


class TestPaymentWebhookDelay:
    """The host paid, but Razorpay's confirmation is late."""

    def test_check_in_waits_for_the_money_then_goes_ahead(self):
        booking = paid_booking()
        record, _ = escrow.start_funding(booking.pk, vendor=booking.vendor)
        assert Escrow.objects.get(pk=record.pk).status == "funding"

        with pytest.raises(Exception, match=r"(?i)fund|escrow|stipend"):
            transition(
                booking.pk,
                BookingStatus.CHECKED_IN,
                actor=Actor.VENDOR,
                user=booking.vendor,
                now=at_start(booking),
            )

        capture(record)  # the webhook finally arrives
        assert Escrow.objects.get(pk=record.pk).status == "held"
        transition(
            booking.pk,
            BookingStatus.CHECKED_IN,
            actor=Actor.VENDOR,
            user=booking.vendor,
            now=at_start(booking),
        )
        assert Booking.objects.get(pk=booking.pk).status == BookingStatus.CHECKED_IN

    def test_money_captured_after_the_booking_was_cancelled_goes_back(
        self, django_capture_on_commit_callbacks
    ):
        booking = paid_booking()
        record, _ = escrow.start_funding(booking.pk, vendor=booking.vendor)
        cancel(booking.pk, user=booking.vendor, by=Actor.VENDOR, reason="emergency", note="Flood.")
        with django_capture_on_commit_callbacks(execute=True):
            capture(record)  # Razorpay confirms a payment for a booking that's gone
        record.refresh_from_db()
        assert record.status != "held"
        assert record.refund_ids  # the refund was asked for at the gateway


class TestDoubleTapOnPay:
    """The host taps Pay twice (or the page retries)."""

    def test_one_order_and_one_charge(self):
        booking = paid_booking()
        first, order_1 = escrow.start_funding(booking.pk, vendor=booking.vendor)
        second, order_2 = escrow.start_funding(booking.pk, vendor=booking.vendor)
        assert (first.pk, order_1) == (second.pk, order_2)
        assert Escrow.objects.filter(booking=booking).count() == 1

        capture(first, event_id="evt_1")
        capture(first, event_id="evt_1")  # the same webhook delivered twice
        capture(first, event_id="evt_2", payment_id="pay_1")  # or re-sent with a new id
        assert LedgerTransaction.objects.filter(kind="escrow_funded").count() == 1

    def test_the_api_answers_both_taps_with_the_same_checkout(self):
        booking = paid_booking()
        api = APIClient()
        api.force_authenticate(booking.vendor)
        url = f"/api/v1/bookings/{booking.pk}/escrow/fund/"
        one, two = api.post(url), api.post(url)
        assert one.status_code == two.status_code == 200
        assert one.json()["order_id"] == two.json()["order_id"]


class TestExpiredOffer:
    """The talent answers an offer after its 48 hours ran out."""

    def test_accepting_too_late_is_refused_clearly(self):
        from apps.applications.models import Application
        from apps.bookings.jobs import expire_offers
        from apps.bookings.tests.helpers import offered
        from apps.offers.services import OfferError, accept, open_offer

        application = offered()
        offer = open_offer(application.pk)
        expire_offers(application.offer_expires_at + timedelta(minutes=1))
        assert Application.objects.get(pk=application.pk).status == "expired"
        with pytest.raises(OfferError):
            accept(offer.pk, user=application.talent)


class TestHostCancelsLate:
    """The host cancels the day before the stay."""

    def test_the_talent_is_refunded_and_it_counts_against_the_host(self):
        from apps.bookings.models import Cancellation

        booking = paid_booking()
        record, _ = escrow.start_funding(booking.pk, vendor=booking.vendor)
        capture(record)
        day_before = at_start(booking) - timedelta(days=1)

        effect = preview(booking, by=Actor.VENDOR, now=day_before)
        assert effect.effect in {"last_minute", "late"}

        cancel(
            booking.pk,
            user=booking.vendor,
            by=Actor.VENDOR,
            reason="emergency",
            note="Burst pipe; the dorm is closed.",
            now=day_before,
        )
        booking.refresh_from_db()
        assert booking.status == BookingStatus.CANCELLED
        recorded = Cancellation.objects.get(booking=booking)
        assert recorded.by == CancelledBy.VENDOR
        assert recorded.effect in {"last_minute", "late"}
        record.refresh_from_db()
        assert record.status != "held"  # the money isn't left sitting in escrow


class TestOfflineDevices:
    """Phones and the arrivals screen lose signal and send things twice."""

    def test_a_check_in_synced_twice_counts_once(self):
        from apps.attendance.models import CheckIn
        from apps.bookings.tests.helpers import booked

        booking = booked()
        attendance_pass = attendance.issue_pass(booking, location=None, now=at_start(booking))
        event = {
            "booking_id": booking.pk,
            "method": "qr",
            "token": attendance.token_for(attendance_pass),
            "code": "",
            "reason": "",
            "scanned_at": at_start(booking),
            "client_id": uuid.uuid4(),
        }
        results = attendance.sync(booking.vendor, [event, event], now=at_start(booking, 11))
        assert [r["status"] for r in results] == ["applied", "duplicate"]
        assert CheckIn.objects.filter(booking=booking).count() == 1

    def test_an_application_sent_twice_is_refused_as_already_applied(self):
        """The app treats this as sent when its own earlier try got through
        (mobile/lib/src/apply/outbox.dart, _sentByAnEarlierTry)."""
        from apps.applications.tests.helpers import dates, eligible_talent, live_gig

        gig, talent = live_gig(), eligible_talent()
        api = APIClient()
        api.force_authenticate(talent)
        body = {"pitch": "Two seasons at hostels.", "answers": [], "attachments": [], **{
            k: v.isoformat() for k, v in dates().items()
        }}  # fmt: skip
        first = api.post(f"/api/v1/gigs/{gig.pk}/applications/", body, format="json")
        again = api.post(f"/api/v1/gigs/{gig.pk}/applications/", body, format="json")
        assert first.status_code == 201
        assert again.status_code == 422
        codes = [r["code"] for r in again.json()["details"]["reasons"]]
        assert codes == ["already_applied"]
        mine = api.get("/api/v1/applications/mine/").json()
        items = mine if isinstance(mine, list) else mine["results"]
        assert [a["id"] for a in items] == [first.json()["id"]]
        assert items[0]["applied_at"]


class TestOtpFailure:
    """The code is wrong, or the OTP provider is down."""

    def test_a_bad_token_is_a_clear_401_and_signs_nobody_in(self):
        response = APIClient().post(
            "/api/v1/auth/exchange/", {"id_token": "not-a-real-token"}, format="json"
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_sign_in_token"

    def test_a_provider_outage_is_a_503_the_app_can_retry(self):
        response = APIClient().post(
            "/api/v1/auth/exchange/", {"id_token": UNAVAILABLE}, format="json"
        )
        assert response.status_code == 503
        assert response.json()["code"] == "auth_provider_unavailable"
