import uuid
from datetime import datetime, time

from django.conf import settings
from django.utils import timezone

from apps.applications.tests.helpers import live_gig
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.services import transition
from apps.bookings.tests.helpers import booked
from apps.gigs.constants import CompensationModel
from apps.money import escrow, webhooks
from apps.money.gateway.fake import signed
from apps.money.ledger import ACCOUNTS
from apps.money.models import Account, Escrow, PayoutAccount

STIPEND = 500_000  # ₹5,000
FEE = 10_000  # 2%
FEE_GST = 1_800  # 18% of the fee
TOTAL = STIPEND + FEE + FEE_GST
# What the gateway itself charges on the payment (GST included).
GATEWAY_FEE, GATEWAY_FEE_TAX = 10_230, 1_560


def ensure_accounts() -> None:
    """The chart of accounts (migration 0003). Transactional tests elsewhere flush it."""
    for code, (name, kind) in ACCOUNTS.items():
        Account.objects.get_or_create(code=code, defaults={"name": name, "kind": kind})


def paid_booking(model=CompensationModel.PAID, **gig):
    gig = live_gig(
        **{
            "compensation_model": model,
            "stipend_amount": 5000,
            "stipend_period": "total",
            "stay_type": "none",
            **gig,
        }
    )
    return booked(gig)


def deliver(event: str, entity_name: str, entity: dict, *, event_id=None, now=None) -> str:
    body, headers = signed(
        {"event": event, "payload": {entity_name: {"entity": entity}}},
        settings.RAZORPAY_ESCROW_WEBHOOK_SECRET,
        event_id or uuid.uuid4().hex,
    )
    return webhooks.handle(body, headers, now=now)


def capture(record: Escrow, *, amount=None, payment_id="pay_1", event_id=None, now=None) -> str:
    return deliver(
        "payment.captured",
        "payment",
        {
            "id": payment_id,
            "order_id": record.gateway_order_id,
            "status": "captured",
            "amount": record.total_paise if amount is None else amount,
            "fee": GATEWAY_FEE,
            "tax": GATEWAY_FEE_TAX,
        },
        event_id=event_id,
        now=now,
    )


def funded(booking=None, *, now=None):
    ensure_accounts()
    booking = booking or paid_booking()
    record, _ = escrow.start_funding(booking.pk, vendor=booking.vendor)
    capture(record, now=now)
    record.refresh_from_db()
    return booking, record


def day_one(booking) -> datetime:
    return timezone.make_aware(datetime.combine(booking.start_date, time(10)))


def check_in(booking, *, delivering=True):
    now = day_one(booking)
    transition(
        booking.pk, BookingStatus.CHECKED_IN, actor=Actor.VENDOR, user=booking.vendor, now=now
    )
    if delivering:
        transition(
            booking.pk, BookingStatus.DELIVERING, actor=Actor.TALENT, user=booking.talent, now=now
        )
    booking.refresh_from_db()
    return booking


def payout_account(talent, *, pan=True, active=True) -> PayoutAccount:
    return PayoutAccount.objects.create(
        talent=talent,
        gateway_account_id=f"acc_{talent.pk.hex[:12]}",
        active=active,
        pan_on_file=pan,
    )
