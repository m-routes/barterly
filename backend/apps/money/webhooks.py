"""Escrow webhooks from the gateway: payment captured or failed, refund processed or
failed. (Payout webhooks come from the payout provider: payouts.py.)

The signature is checked first (the gateway's parse_webhook). Each event is stored as a
GatewayEvent under its unique event id in the same transaction as its effects, so a
redelivered event changes nothing; the ledger's idempotency keys are a second guard.
Webhooks are handled even while the kill switch is on: money that moved at the gateway
must be recorded.

Anything unexpected (an amount that doesn't match, a refund we didn't ask for) is
recorded with its outcome and raised as an alert for a person, never guessed at.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.services.audit import log_action, snapshot
from apps.money import alerts, ledger
from apps.money.escrow import AUDIT, RELEASABLE, _event, refund_or_flag
from apps.money.gateway.base import GatewayEventData, get_gateway
from apps.money.ledger import (
    ESCROW,
    FEE_RECOVERY,
    GATEWAY,
    GATEWAY_FEES,
    GST_INPUT,
    GST_OUTPUT,
    Line,
)
from apps.money.models import Escrow, EscrowStatus, GatewayEvent

log = logging.getLogger(__name__)
E = EscrowStatus


def handle(body: bytes, headers, now=None) -> str:
    """Verify and apply one webhook. Raises GatewayError on a bad signature."""
    data = get_gateway().parse_webhook(body, headers)
    now = now or timezone.now()
    try:
        with transaction.atomic():
            record = GatewayEvent.objects.create(
                event_id=data.event_id, event=data.event, payload=data.raw, received_at=now
            )
            outcome = HANDLERS.get(data.event, _ignored)(data, now)
            record.outcome = outcome[:200]
            record.save(update_fields=["outcome"])
    except IntegrityError:
        if GatewayEvent.objects.filter(event_id=data.event_id).exists():
            return "duplicate"
        raise
    return outcome


def _ignored(data: GatewayEventData, now) -> str:
    return "ignored"


def _alert(what: str, data: GatewayEventData, escrow: Escrow | None = None) -> str:
    alerts.raise_alert(
        f"Escrow webhook {data.event}: {what}", {"event_id": data.event_id}, obj=escrow
    )
    return f"alert: {what}"


# ---------- Payments ----------


def payment_captured(data: GatewayEventData, now) -> str:
    payment = data.payment
    escrow = (
        Escrow.objects.select_for_update()
        .select_related("booking__gig")
        .filter(gateway_order_id=payment.get("order_id") or "-")
        .first()
    )
    if escrow is None:
        return "not an escrow payment"
    if escrow.status == E.HELD and escrow.gateway_payment_id == payment.get("id"):
        return "already held"
    if escrow.status not in (E.FUNDING, E.AWAITING_FUNDING):
        return _alert(f"a second payment for escrow {escrow.pk}; refund it by hand", data, escrow)
    amount = int(payment.get("amount") or 0)
    if amount != escrow.total_paise:
        return _alert(f"paid {amount}, expected {escrow.total_paise}", data, escrow)
    fee = int(payment.get("fee") or 0)  # the gateway's fee, GST included
    fee_tax = int(payment.get("tax") or 0)
    lines = [Line(GATEWAY, ESCROW, escrow.stipend_paise)]
    if escrow.fee_paise:
        lines.append(Line(GATEWAY, FEE_RECOVERY, escrow.fee_paise))
    if escrow.fee_gst_paise:
        lines.append(Line(GATEWAY, GST_OUTPUT, escrow.fee_gst_paise))
    if fee - fee_tax > 0:
        lines.append(Line(GATEWAY_FEES, GATEWAY, fee - fee_tax))
    if fee_tax > 0:
        lines.append(Line(GST_INPUT, GATEWAY, fee_tax))
    ledger.post(
        "escrow_funded",
        f"captured:{payment['id']}",
        lines,
        booking=escrow.booking,
        reference=payment["id"],
        now=now,
    )
    before = snapshot(escrow, AUDIT)
    escrow.status, escrow.gateway_payment_id, escrow.funded_at = E.HELD, payment["id"], now
    escrow.save()
    log_action(
        actor=None,
        action="money.funded",
        obj=escrow,
        before=before,
        after={**snapshot(escrow, AUDIT), "payment_id": payment["id"], "total_paise": amount},
    )
    booking = escrow.booking
    _event(
        "money.funded",
        escrow,
        booking,
        now=now,
        key="funded",
        stipend_paise=escrow.stipend_paise,
        notify=["talent", "vendor"],
    )
    if booking.status != "confirmed" and booking.status not in RELEASABLE:
        # Paid after the booking ended (cancelled while the payment was in flight).
        transaction.on_commit(
            lambda: refund_or_flag(booking.pk, reason="Paid after the booking ended.", now=now)
        )
    return "held"


def payment_failed(data: GatewayEventData, now) -> str:
    payment = data.payment
    escrow = Escrow.objects.filter(gateway_order_id=payment.get("order_id") or "-").first()
    if escrow is None:
        return "not an escrow payment"
    log_action(
        actor=None,
        action="money.payment_failed",
        obj=escrow,
        after={"payment_id": payment.get("id", ""), "reason": payment.get("error_description", "")},
    )
    # The order stays open: the host can try again with another method.
    _event(
        "money.payment_failed",
        escrow,
        escrow.booking,
        now=now,
        key=payment.get("id", ""),
        notify=["vendor"],
    )
    return "payment failed"


# ---------- Refunds ----------


def refund_processed(data: GatewayEventData, now) -> str:
    refund = data.refund
    escrow = (
        Escrow.objects.select_for_update()
        .filter(gateway_payment_id=refund.get("payment_id") or "-")
        .first()
    )
    if escrow is None:
        return "not an escrow payment"
    if refund.get("id") not in escrow.refund_ids:
        return _alert(f"refund {refund.get('id')} wasn't made by Barterly", data, escrow)
    amount = int(refund.get("amount") or 0)
    ledger.post(
        "refund_processed",
        f"refund:{refund['id']}",
        [Line(ESCROW, GATEWAY, amount)],
        booking=escrow.booking,
        reference=refund["id"],
        now=now,
    )
    log_action(
        actor=None,
        action="money.refund_processed",
        obj=escrow,
        after={"refund_id": refund["id"], "amount_paise": amount},
    )
    return "refund recorded"


def refund_failed(data: GatewayEventData, now) -> str:
    escrow = Escrow.objects.filter(gateway_payment_id=data.refund.get("payment_id") or "-").first()
    if escrow is None:
        return "not an escrow payment"
    return _alert(f"refund {data.refund.get('id')} failed; retry it by hand", data, escrow)


HANDLERS = {
    "payment.captured": payment_captured,
    "payment.failed": payment_failed,
    "refund.processed": refund_processed,
    "refund.failed": refund_failed,
}
