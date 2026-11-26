"""Webhooks: signatures, idempotency, and the cases that need a person."""

import pytest
from django.conf import settings

from apps.common.models import AuditLog
from apps.money import escrow, ledger
from apps.money.gateway.base import GatewayError
from apps.money.gateway.fake import signed
from apps.money.models import EscrowStatus, GatewayEvent, LedgerTransaction
from apps.money.tests.helpers import TOTAL, capture, deliver, funded, paid_booking
from apps.money.webhooks import handle
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def started():
    booking = paid_booking()
    record, _ = escrow.start_funding(booking.pk, vendor=booking.vendor)
    return booking, record


def alerts():
    return AuditLog.objects.filter(action="money.alert")


class TestSignatures:
    def test_a_bad_signature_is_refused_and_not_stored(self):
        body, headers = signed({"event": "payment.captured"}, "wrong-secret", "evt_1")
        with pytest.raises(GatewayError, match="signature"):
            handle(body, headers)
        assert not GatewayEvent.objects.exists()

    def test_an_event_needs_its_id(self):
        body, headers = signed(
            {"event": "payment.captured"}, settings.RAZORPAY_ESCROW_WEBHOOK_SECRET, ""
        )
        with pytest.raises(GatewayError, match="event id"):
            handle(body, headers)

    def test_an_unset_secret_refuses_everything(self, settings):
        body, headers = signed({"event": "x"}, settings.RAZORPAY_ESCROW_WEBHOOK_SECRET, "e")
        settings.RAZORPAY_ESCROW_WEBHOOK_SECRET = ""
        with pytest.raises(GatewayError):
            handle(body, headers)


class TestIdempotency:
    def test_a_redelivered_event_changes_nothing(self):
        _, record = started()
        assert capture(record, event_id="evt_same") == "held"
        assert capture(record, event_id="evt_same") == "duplicate"
        assert capture(record, event_id="evt_other") == "already held"
        assert LedgerTransaction.objects.count() == 1
        assert GatewayEvent.objects.count() == 2
        assert ledger.is_balanced()

    def test_unknown_events_are_stored_and_ignored(self):
        assert deliver("order.paid", "order", {"id": "order_x"}) == "ignored"
        assert GatewayEvent.objects.get().outcome == "ignored"


class TestPayments:
    def test_a_wrong_amount_is_held_back_for_a_person(self, mailoutbox, settings):
        settings.ESCROW_ALERT_EMAILS = ["money@barterly.test"]
        _, record = started()
        assert capture(record, amount=TOTAL - 1).startswith("alert")
        record.refresh_from_db()
        assert record.status == EscrowStatus.FUNDING
        assert not LedgerTransaction.objects.exists()
        assert alerts().count() == 1
        assert mailoutbox[0].to == ["money@barterly.test"]

    def test_a_second_payment_for_a_held_escrow_raises_an_alert(self):
        _, record = funded()
        assert capture(record, payment_id="pay_2").startswith("alert")
        assert LedgerTransaction.objects.count() == 1

    def test_payments_for_other_orders_are_not_ours(self):
        assert deliver("payment.captured", "payment", {"id": "p", "order_id": "order_sub"}) == (
            "not an escrow payment"
        )

    def test_a_failed_payment_tells_the_host_and_keeps_the_order(self):
        booking, record = started()
        outcome = deliver(
            "payment.failed",
            "payment",
            {
                "id": "pay_f",
                "order_id": record.gateway_order_id,
                "error_description": "Card declined",
            },
        )
        assert outcome == "payment failed"
        record.refresh_from_db()
        assert record.status == EscrowStatus.FUNDING
        assert Notification.objects.filter(
            kind="money.payment_failed", user=booking.vendor
        ).exists()
        assert AuditLog.objects.filter(action="money.payment_failed").exists()


class TestRefunds:
    def test_a_refund_barterly_didnt_make_raises_an_alert(self):
        funded()
        assert deliver(
            "refund.processed", "refund", {"id": "rfnd_dash", "payment_id": "pay_1", "amount": 100}
        ).startswith("alert")
        assert ledger.balance(ledger.ESCROW) == 500_000

    def test_a_failed_refund_raises_an_alert(self):
        funded()
        assert deliver(
            "refund.failed", "refund", {"id": "rfnd_1", "payment_id": "pay_1"}
        ).startswith("alert")
        assert alerts().count() == 1

    def test_refunds_for_unknown_payments_are_not_ours(self):
        for event, name in [
            ("refund.processed", "refund"),
            ("refund.failed", "refund"),
        ]:
            assert deliver(event, name, {"id": "x", "payment_id": "nope"}).startswith(
                "not an escrow"
            )
