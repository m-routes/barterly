"""Escrow for hybrid and paid bookings: fund, hold, release (or refund), pay out.

1. quote(): the stipend from the agreement in force (prorated by day for weekly and
   monthly stipends), plus the gateway's fee and GST on that fee, which the host pays.
2. start_funding(): a gateway order for the total; the host pays it at checkout.
   The money is held once the gateway says it's captured (webhooks.py). A paid or
   hybrid booking can't check in until it is.
3. Release, on the host approving the deliverables, or automatically
   ESCROW_AUTO_RELEASE_HOURS after the latest submission with no answer
   (auto_release()). The stipend is split: platform commission (ESCROW_COMMISSION_BPS)
   + GST on the commission + TDS (ESCROW_TDS_*) + the talent's payout, which goes to
   their payout account by a transfer (send_payout()).
4. A dispute freezes the escrow; only an admin decision releases, splits or refunds it.
   A booking cancelled before any release is refunded to the host (the gateway's fee is
   not refundable).

The kill switch (settings.ESCROW_PAUSED, or EscrowControl in admin) stops new funding,
releases, payouts and refunds; webhooks are still recorded.

CA REVIEW NEEDED: the commission, GST and TDS settings are placeholders for your
chartered accountant to confirm.

Locks: the booking, then its escrow (the same order as bookings.services). Every
change is audited (money.<what>), and every money movement is a ledger.post().
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action, snapshot
from apps.gigs.constants import STIPEND_MODELS, StipendPeriod
from apps.money import ledger
from apps.money.gateway.base import GatewayError, get_gateway
from apps.money.ledger import (
    COMMISSION,
    ESCROW,
    GATEWAY,
    GST_OUTPUT,
    TALENT,
    TDS,
    Line,
    rupees_to_paise,
    share,
)
from apps.money.models import (
    Escrow,
    EscrowControl,
    EscrowStatus,
    PayoutAccount,
    PayoutStatus,
)

E = EscrowStatus
AUDIT = ["status", "payout_status", "frozen", "released_paise", "refund_paise"]
# Booking states in which a release can happen (the work has started or ended).
RELEASABLE = frozenset(
    {
        BookingStatus.CHECKED_IN,
        BookingStatus.DELIVERING,
        BookingStatus.COMPLETED,
        BookingStatus.REVIEWED,
        BookingStatus.DISPUTED,
    }
)

# What an admin can decide about a held escrow.
DECISIONS = (
    ("release", "Release to the talent"),
    ("split", "Split"),
    ("refund", "Refund the host"),
)
# States in which a payout is owed to the talent.
PAID_STATES = (E.RELEASED, E.SPLIT)


class EscrowError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------- The kill switch ----------


def paused() -> bool:
    if settings.ESCROW_PAUSED:
        return True
    control = EscrowControl.objects.filter(pk=1).first()
    return bool(control and control.paused)


def set_paused(value: bool, *, by, reason: str = "") -> EscrowControl:
    control, _ = EscrowControl.objects.get_or_create(pk=1)
    before = {"paused": control.paused}
    control.paused, control.reason = value, reason[:300]
    control.changed_by, control.changed_at = by, timezone.now()
    control.save()
    log_action(
        actor=by,
        action="money.kill_switch",
        obj=control,
        before=before,
        after={"paused": value, "reason": reason},
    )
    return control


def _not_paused(what: str) -> None:
    if paused():
        raise EscrowError(f"{what} is paused for now. Try again later.", 503)


# ---------- Quote ----------


def needs_escrow(booking: Booking) -> bool:
    return booking.gig.compensation_model in STIPEND_MODELS


def _terms(booking: Booking) -> dict:
    agreement = getattr(booking, "agreement", None)
    version = agreement and (
        agreement.current_version or agreement.versions.order_by("-number").first()
    )
    if version is None:
        raise EscrowError("This booking has no agreement to take the stipend from.")
    return version.terms


def prorate(amount: int, numerator: int, denominator: int) -> int:
    """amount x numerator / denominator, rounded half up (integers only)."""
    return (amount * numerator * 2 + denominator) // (2 * denominator)


def stipend_for(terms: dict) -> int:
    from datetime import date

    if terms.get("stipend_amount") in (None, ""):
        raise EscrowError("This agreement has no stipend.")
    amount = rupees_to_paise(terms["stipend_amount"])
    days = (date.fromisoformat(terms["end_date"]) - date.fromisoformat(terms["start_date"])).days
    period = terms.get("stipend_period")
    if period == StipendPeriod.PER_WEEK:
        return prorate(amount, days, 7)
    if period == StipendPeriod.PER_MONTH:
        return prorate(amount, days, 30)
    return amount


def quote(booking: Booking) -> dict:
    stipend = stipend_for(_terms(booking))
    fee = share(stipend, settings.ESCROW_GATEWAY_FEE_BPS)
    fee_gst = share(fee, settings.ESCROW_GST_BPS)
    return {"stipend": stipend, "fee": fee, "fee_gst": fee_gst, "total": stipend + fee + fee_gst}


def split(amount: int, *, pan_on_file: bool) -> dict:
    """How a released amount divides. Pure; integers only."""
    commission = share(amount, settings.ESCROW_COMMISSION_BPS)
    commission_gst = share(commission, settings.ESCROW_GST_BPS)
    tds = 0
    if settings.ESCROW_TDS_ENABLED and amount >= settings.ESCROW_TDS_THRESHOLD_PAISE:
        bps = settings.ESCROW_TDS_BPS if pan_on_file else settings.ESCROW_TDS_NO_PAN_BPS
        tds = share(amount, bps)
    payout = amount - commission - commission_gst - tds
    if payout <= 0:
        raise EscrowError("Nothing would be left for the talent.")
    return {
        "commission": commission,
        "commission_gst": commission_gst,
        "tds": tds,
        "payout": payout,
    }


# ---------- Funding ----------


def _lock(booking_id) -> tuple[Booking, Escrow | None]:
    booking = (
        Booking.objects.select_for_update(of=("self",))
        .select_related("gig", "agreement__current_version")
        .get(pk=booking_id)
    )
    escrow = Escrow.objects.select_for_update().filter(booking=booking).first()
    return booking, escrow


def _audit(escrow: Escrow, action: str, before: dict, *, actor=None, **extra) -> None:
    log_action(
        actor=actor,
        action=f"money.{action}",
        obj=escrow,
        before=before,
        after={**snapshot(escrow, AUDIT), **extra},
    )


def _event(name: str, escrow: Escrow, booking: Booking, *, now, **extra) -> None:
    publish(
        DomainEvent(
            name,
            {
                "booking_id": str(booking.pk),
                "escrow_id": str(escrow.pk),
                "gig_title": booking.gig.title,
                "talent_id": str(booking.talent_id),
                "vendor_id": str(booking.vendor_id),
                "dedup_key": f"{name}:{escrow.pk}:{extra.pop('key', '')}",
                **extra,
            },
            occurred_at=now,
        )
    )


def start_funding(booking_id, *, vendor, request=None, now=None) -> tuple[Escrow, str]:
    """A gateway order for the host to pay. Returns the escrow and the order id; asking
    again before it's paid returns the same order."""
    now = now or timezone.now()
    _not_paused("Funding")
    with transaction.atomic():
        booking, escrow = _lock(booking_id)
        if booking.vendor_id != vendor.pk:
            raise Booking.DoesNotExist
        if not needs_escrow(booking):
            raise EscrowError("This gig has no stipend to fund.")
        if booking.status != BookingStatus.CONFIRMED:
            raise EscrowError("Fund the stipend once the booking is confirmed, before check-in.")
        if escrow and escrow.status not in (E.AWAITING_FUNDING, E.FUNDING):
            raise EscrowError("The stipend is already funded.")
        if escrow and escrow.status == E.FUNDING and escrow.gateway_order_id:
            return escrow, escrow.gateway_order_id
        amounts = quote(booking)
        if escrow is None:
            escrow = Escrow(booking=booking, created_at=now)
        before = snapshot(escrow, AUDIT) if escrow.pk else {}
        escrow.stipend_paise, escrow.fee_paise = amounts["stipend"], amounts["fee"]
        escrow.fee_gst_paise, escrow.total_paise = amounts["fee_gst"], amounts["total"]
        try:
            order = get_gateway().create_order(
                amount_paise=escrow.total_paise,
                receipt=f"escrow-{booking.pk}",
                notes={"booking_id": booking.pk},
            )
        except GatewayError as exc:
            raise EscrowError(str(exc), 502) from exc
        escrow.gateway_order_id = order.id
        escrow.status = E.FUNDING
        escrow.save()
        _audit(
            escrow,
            "funding_started",
            before,
            actor=vendor,
            order_id=order.id,
            total_paise=escrow.total_paise,
        )
    return escrow, order.id


def require_funded(booking: Booking) -> str | None:
    """The check-in guard: a paid or hybrid booking needs its stipend held first."""
    if not needs_escrow(booking):
        return None
    escrow = Escrow.objects.filter(booking=booking).first()
    if escrow is None or escrow.status != E.HELD:
        return "The host needs to fund the stipend before check-in."
    return None


# ---------- Release and payout ----------


def release(
    booking_id,
    *,
    by: str,
    actor=None,
    amount: int | None = None,
    request=None,
    now=None,
    admin_decision: bool = False,
) -> Escrow:
    """Release `amount` (all that's held by default) to the talent, split into
    commission, GST, TDS and payout; then send the payout."""
    now = now or timezone.now()
    _not_paused("Releasing money")
    with transaction.atomic():
        booking, escrow = _lock(booking_id)
        if escrow is None or escrow.status != E.HELD:
            raise EscrowError("There's no held stipend to release.")
        if escrow.frozen and not admin_decision:
            raise EscrowError("A dispute is open: an admin decides what happens to the money.")
        if booking.status not in RELEASABLE:
            raise EscrowError("Money is released once the stay has started.")
        amount = escrow.unreleased_paise if amount is None else ledger.check_paise(amount)
        if not 0 < amount <= escrow.unreleased_paise:
            raise EscrowError("That's more than is held.", 400)
        account = PayoutAccount.objects.filter(talent_id=booking.talent_id).first()
        parts = split(amount, pan_on_file=bool(account and account.pan_on_file))
        before = snapshot(escrow, AUDIT)
        ledger.post(
            "escrow_released",
            f"release:{escrow.pk}",
            [
                Line(ESCROW, COMMISSION, parts["commission"]),
                *(
                    [Line(ESCROW, GST_OUTPUT, parts["commission_gst"])]
                    if parts["commission_gst"]
                    else []
                ),
                *([Line(ESCROW, TDS, parts["tds"])] if parts["tds"] else []),
                Line(ESCROW, TALENT, parts["payout"]),
            ],
            booking=booking,
            memo=f"Released by {by}",
            now=now,
        )
        escrow.released_paise = amount
        escrow.commission_paise = parts["commission"]
        escrow.commission_gst_paise = parts["commission_gst"]
        escrow.tds_paise = parts["tds"]
        escrow.payout_paise = parts["payout"]
        escrow.released_at, escrow.released_by = now, by
        escrow.status = E.RELEASED
        escrow.frozen = False
        escrow.save()
        _audit(escrow, "released", before, actor=actor, by=by, **parts)
        _event(
            "money.released",
            escrow,
            booking,
            now=now,
            key="release",
            payout_paise=parts["payout"],
            notify=["talent", "vendor"],
        )
        transaction.on_commit(lambda: send_payout(escrow.pk))
    return escrow


def send_payout(escrow_id, now=None) -> Escrow:
    """Transfer the talent's payout. Marked `sending` in its own commit before the call,
    so a crash mid-call can't send twice: a stuck `sending` is left for a person (the
    reconciliation shows whether the transfer happened)."""
    now = now or timezone.now()
    with transaction.atomic():
        escrow = Escrow.objects.select_for_update().select_related("booking").get(pk=escrow_id)
        if escrow.status not in PAID_STATES or escrow.payout_status in (
            PayoutStatus.SENT,
            PayoutStatus.SETTLED,
            PayoutStatus.SENDING,
        ):
            return escrow
        if paused():
            escrow.payout_status = PayoutStatus.PAUSED
            escrow.save(update_fields=["payout_status", "updated_at"])
            return escrow
        account = PayoutAccount.objects.filter(
            talent_id=escrow.booking.talent_id, active=True
        ).first()
        if account is None:
            escrow.payout_status = PayoutStatus.WAITING_FOR_ACCOUNT
            escrow.save(update_fields=["payout_status", "updated_at"])
            return escrow
        escrow.payout_status = PayoutStatus.SENDING
        escrow.save(update_fields=["payout_status", "updated_at"])
    try:
        transfer_id = get_gateway().transfer(
            account_id=account.gateway_account_id,
            amount_paise=escrow.payout_paise,
            notes={"booking_id": escrow.booking_id, "escrow_id": escrow.pk},
        )
    except GatewayError:
        Escrow.objects.filter(pk=escrow.pk).update(payout_status=PayoutStatus.FAILED)
        log_action(
            actor=None,
            action="money.payout_failed",
            obj=escrow,
            after={"payout_paise": escrow.payout_paise},
        )
        escrow.refresh_from_db()
        return escrow
    with transaction.atomic():
        escrow = Escrow.objects.select_for_update().get(pk=escrow_id)
        ledger.post(
            "payout_sent",
            f"payout:{escrow.pk}:{transfer_id}",
            [Line(TALENT, GATEWAY, escrow.payout_paise)],
            booking=escrow.booking,
            reference=transfer_id,
            now=now,
        )
        before = snapshot(escrow, AUDIT)
        escrow.payout_status, escrow.payout_transfer_id = PayoutStatus.SENT, transfer_id
        escrow.save(update_fields=["payout_status", "payout_transfer_id", "updated_at"])
        _audit(
            escrow, "payout_sent", before, transfer_id=transfer_id, payout_paise=escrow.payout_paise
        )
    return escrow


def retry_payouts(now=None) -> dict[str, int]:
    """Job: payouts waiting for an account, paused, or failed get another go."""
    waiting = Escrow.objects.filter(
        status__in=PAID_STATES,
        payout_status__in=(
            PayoutStatus.WAITING_FOR_ACCOUNT,
            PayoutStatus.PAUSED,
            PayoutStatus.FAILED,
            PayoutStatus.NONE,
        ),
    ).values_list("pk", flat=True)
    sent = 0
    for pk in list(waiting[:200]):
        if send_payout(pk, now=now).payout_status == PayoutStatus.SENT:
            sent += 1
    return {"payouts_sent": sent}


# ---------- Refunds and disputes ----------


def refund(
    booking_id,
    *,
    amount: int | None = None,
    by: str,
    actor=None,
    reason: str = "",
    now=None,
    admin_decision: bool = False,
) -> Escrow:
    """Refund the host from what's held (all of it by default). The ledger records it
    when the gateway confirms (refund.processed)."""
    now = now or timezone.now()
    _not_paused("Refunding")
    with transaction.atomic():
        booking, escrow = _lock(booking_id)
        if escrow is None or escrow.status != E.HELD:
            raise EscrowError("There's no held stipend to refund.")
        if escrow.frozen and not admin_decision:
            raise EscrowError("A dispute is open: an admin decides what happens to the money.")
        amount = escrow.unreleased_paise if amount is None else ledger.check_paise(amount)
        if not 0 < amount <= escrow.unreleased_paise:
            raise EscrowError("That's more than is held.", 400)
        try:
            refund_id = get_gateway().refund(
                payment_id=escrow.gateway_payment_id,
                amount_paise=amount,
                notes={"booking_id": booking.pk, "reason": reason[:200]},
            )
        except GatewayError as exc:
            raise EscrowError(str(exc), 502) from exc
        before = snapshot(escrow, AUDIT)
        escrow.refund_paise += amount
        escrow.refund_ids = [*escrow.refund_ids, refund_id]
        if escrow.unreleased_paise == 0 and escrow.released_paise == 0:
            escrow.status = E.REFUNDED
        escrow.frozen = False
        escrow.save()
        _audit(
            escrow,
            "refunded",
            before,
            actor=actor,
            by=by,
            amount_paise=amount,
            refund_id=refund_id,
            reason=reason,
        )
        _event(
            "money.refunded",
            escrow,
            booking,
            now=now,
            key=refund_id,
            amount_paise=amount,
            notify=["vendor"],
        )
    return escrow


def freeze(booking_id, *, reason: str, now=None) -> Escrow | None:
    now = now or timezone.now()
    _, escrow = _lock(booking_id)
    if escrow is None or escrow.status != E.HELD or escrow.frozen:
        return escrow
    before = snapshot(escrow, AUDIT)
    escrow.frozen, escrow.frozen_reason = True, reason[:300]
    escrow.save(update_fields=["frozen", "frozen_reason", "updated_at"])
    _audit(escrow, "frozen", before, reason=reason)
    return escrow


def decide(
    booking_id, *, decision: str, admin, talent_paise: int | None = None, note: str = "", now=None
) -> Escrow:
    """An admin's call on a disputed (or any held) escrow: release, split or refund."""
    now = now or timezone.now()
    if not note.strip():
        raise EscrowError("Say why.", 400)
    with transaction.atomic():
        booking, escrow = _lock(booking_id)
        if escrow is None or escrow.status != E.HELD:
            raise EscrowError("There's no held stipend to decide on.")
        held = escrow.unreleased_paise
        log_action(
            actor=admin,
            action="money.admin_decision",
            obj=escrow,
            after={"decision": decision, "talent_paise": talent_paise, "note": note},
        )
        if decision == "release":
            return release(booking_id, by="admin", actor=admin, now=now, admin_decision=True)
        if decision == "refund":
            return refund(
                booking_id, by="admin", actor=admin, reason=note, now=now, admin_decision=True
            )
        if decision == "split":
            if talent_paise is None or not 0 < ledger.check_paise(talent_paise) < held:
                raise EscrowError("Give the talent's share: more than 0, less than all.", 400)
            # Check the split works out before any money goes back to the host.
            account = PayoutAccount.objects.filter(talent_id=booking.talent_id).first()
            split(talent_paise, pan_on_file=bool(account and account.pan_on_file))
            refund(
                booking_id,
                amount=held - talent_paise,
                by="admin",
                actor=admin,
                reason=note,
                now=now,
                admin_decision=True,
            )
            escrow = release(
                booking_id,
                by="admin",
                actor=admin,
                amount=talent_paise,
                now=now,
                admin_decision=True,
            )
            Escrow.objects.filter(pk=escrow.pk).update(status=E.SPLIT)
            escrow.refresh_from_db()
            return escrow
        raise EscrowError("Decide release, split or refund.", 400)


# ---------- Reacting to bookings ----------


def on_booking_event(event: DomainEvent) -> None:
    """Disputes freeze the escrow; a cancellation before any release refunds the host."""
    booking_id = event.payload.get("booking_id")
    if not booking_id:
        return
    if event.name == "booking.disputed":
        freeze(
            booking_id, reason=event.payload.get("reason", "") or "Disputed", now=event.occurred_at
        )
    elif event.name == "booking.cancelled":
        escrow = Escrow.objects.filter(booking_id=booking_id).first()
        if escrow and escrow.status == E.HELD and escrow.released_paise == 0:
            refund_or_flag(booking_id, reason="The booking was cancelled.", now=event.occurred_at)


def refund_or_flag(booking_id, *, reason: str, now) -> None:
    """Refund the host automatically; if that can't happen now (kill switch, gateway
    down), leave an audit entry for the team instead of blocking the caller."""
    try:
        refund(booking_id, by="system", reason=reason, now=now)
    except EscrowError as exc:
        escrow = Escrow.objects.filter(booking_id=booking_id).first()
        log_action(
            actor=None,
            action="money.refund_needed",
            obj=escrow,
            after={"reason": reason, "why_not_automatic": exc.message},
        )


# ---------- Auto-release ----------


def auto_release(now) -> dict[str, int]:
    """Job: release escrows whose latest submission has had no answer for
    ESCROW_AUTO_RELEASE_HOURS."""
    if paused():
        return {"released": 0, "paused": 1}
    from apps.money.models import DeliverableSubmission, SubmissionReview

    cutoff = now - timedelta(hours=settings.ESCROW_AUTO_RELEASE_HOURS)
    released = 0
    for escrow in Escrow.objects.filter(status=E.HELD, frozen=False).select_related("booking"):
        latest = DeliverableSubmission.objects.filter(booking_id=escrow.booking_id).first()
        if latest is None:
            continue
        due = latest.review == SubmissionReview.PENDING and latest.submitted_at <= cutoff
        # Approved, but the release couldn't happen then (kill switch, say): try again.
        if not (due or latest.review == SubmissionReview.APPROVED):
            continue
        if (
            escrow.booking.status not in RELEASABLE
            or escrow.booking.status == BookingStatus.DISPUTED
        ):
            continue
        try:
            by = "vendor" if latest.review == SubmissionReview.APPROVED else "system"
            release(escrow.booking_id, by=by, now=now)
            released += 1
        except EscrowError:
            continue
    return {"released": released}
