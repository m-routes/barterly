"""Paying talent what a release owes them, through the payout provider.

A payout run goes over the escrows with a payout owed. For each one it pays, holds it
back with a reason, or leaves it for later:
- the kill switch is on: `paused`;
- no verified payout account: `waiting_for_account`;
- the account changed less than 24 hours ago, or this would be the talent's first
  payout and their ID isn't verified: `on_hold`;
- a failed attempt is waiting out its back-off, or ran out of attempts (then an admin
  retries it).

Runs happen after each release, on a schedule (`payout_run` job), when a talent asks
(on demand) and when an admin starts one. Running twice, or twice at once, pays once:
each escrow is locked while its attempt is made, the database allows one live attempt
per escrow, and the provider's idempotency key is the attempt's id.

Each attempt is a Payout row, committed as `creating` before the provider is called. A
crash after that leaves it `creating`; the next run sends it again with the same
idempotency key, which returns the payout already made instead of paying twice.

Ledger: when the provider accepts a payout, Dr talent payable / Cr gateway. If it then
fails or the bank reverses it, the reverse is posted and a new attempt follows.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action, snapshot
from apps.money import ledger
from apps.money.escrow import AUDIT, PAID_STATES, paused
from apps.money.gateway.base import GatewayError
from apps.money.gateway.payouts import DONE, FAILED_STATES, get_provider
from apps.money.ledger import GATEWAY, TALENT, Line
from apps.money.models import (
    Escrow,
    EscrowStatus,
    Payout,
    PayoutAccount,
    PayoutRun,
    PayoutStatus,
    PayoutTrigger,
    ValidationStatus,
)
from apps.money.models import PayoutAttemptStatus as A

log = logging.getLogger(__name__)
P = PayoutStatus
# Escrows whose payout is with the provider or done: nothing to do.
UNDER_WAY = (P.SENDING, P.SENT, P.SETTLED)
STUCK_AFTER = timedelta(minutes=10)
# Wait before each retry of a failed payout; after the last, an admin decides.
BACKOFF = (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=4), timedelta(hours=12))


class PayoutError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------- Rules ----------


def id_verified(talent_id) -> bool:
    from apps.verification.constants import BadgeKind
    from apps.verification.models import Badge

    return Badge.objects.filter(
        user_id=talent_id, kind=BadgeKind.ID_VERIFIED, revoked_at__isnull=True
    ).exists()


def hold_reason(talent_id, account: PayoutAccount | None, now) -> tuple[str, str] | None:
    """Why a payout to this talent can't go now: (escrow payout status, reason code)."""
    if paused():
        return P.PAUSED, "paused"
    if (
        account is None
        or not account.active
        or (account.validation_status != ValidationStatus.VERIFIED)
    ):
        return P.WAITING_FOR_ACCOUNT, "no_verified_account"
    if account.hold_until and account.hold_until > now:
        return P.ON_HOLD, "account_recently_changed"
    first = not Payout.objects.filter(talent_id=talent_id, status=A.PROCESSED).exists()
    if first and not id_verified(talent_id):
        return P.ON_HOLD, "id_not_verified"
    return None


HOLD_MESSAGES = {
    "paused": "Payouts are paused for now.",
    "no_verified_account": "Add a payout account and wait for it to be verified.",
    "account_recently_changed": "Your payout account changed recently, so payouts wait 24 hours.",
    "id_not_verified": "Verify your ID to get your first payout.",
}


# ---------- Runs ----------


def run(
    trigger: str, *, now=None, talent=None, by=None, escrow_ids=None, force: bool = False
) -> PayoutRun:
    now = now or timezone.now()
    record = PayoutRun.objects.create(trigger=trigger, talent=talent, started_by=by, started_at=now)
    if escrow_ids is None:
        _resend_stuck(now)
    owed = Escrow.objects.filter(status__in=PAID_STATES).exclude(payout_status__in=UNDER_WAY)
    if talent is not None:
        owed = owed.filter(booking__talent=talent)
    if escrow_ids is not None:
        owed = owed.filter(pk__in=escrow_ids)
    reasons: dict[str, int] = {}
    for escrow_id in list(owed.values_list("pk", flat=True)[: settings.PAYOUT_RUN_LIMIT]):
        outcome, amount = pay(escrow_id, run=record, now=now, force=force)
        if outcome == "skipped":
            continue
        record.considered += 1
        if outcome == "sent":
            record.sent += 1
            record.sent_paise += amount
        elif outcome == "failed":
            record.failed += 1
        else:
            record.held += 1
            reason = outcome.removeprefix("held:")
            reasons[reason] = reasons.get(reason, 0) + 1
    record.held_reasons, record.finished_at = reasons, timezone.now()
    record.save()
    return record


def scheduled(now) -> dict[str, int]:
    """Job: pay everything owed (and resend anything stuck)."""
    record = run(PayoutTrigger.SCHEDULED, now=now)
    return {"sent": record.sent, "held": record.held, "failed": record.failed}


def after_release(escrow_id) -> None:
    run(PayoutTrigger.RELEASE, escrow_ids=[escrow_id])


def request_payout(talent, *, now=None) -> PayoutRun:
    """On demand: the talent asks for what's available to be paid now."""
    now = now or timezone.now()
    since = now - timedelta(minutes=settings.PAYOUT_ON_DEMAND_EVERY_MINUTES)
    if PayoutRun.objects.filter(
        talent=talent, trigger=PayoutTrigger.ON_DEMAND, started_at__gt=since
    ).exists():
        raise PayoutError("You asked for a payout a moment ago. Try again in a few minutes.", 429)
    return run(PayoutTrigger.ON_DEMAND, talent=talent, by=talent, now=now)


def retry(payout_id, *, admin, note: str, now=None) -> PayoutRun:
    """An admin retries a failed payout now, whatever its back-off or attempts left."""
    if not note.strip():
        raise PayoutError("Say why you're retrying.", 400)
    payout = Payout.objects.select_related("escrow").get(pk=payout_id)
    latest = payout.escrow.payouts.order_by("-attempt").first()
    if payout.status not in (A.FAILED, A.REVERSED) or latest.pk != payout.pk:
        raise PayoutError("Only the latest failed payout can be retried.")
    log_action(
        actor=admin,
        action="money.payout_retry",
        obj=payout,
        after={"note": note, "reason": payout.failure_reason},
    )
    return run(PayoutTrigger.ADMIN, by=admin, escrow_ids=[payout.escrow_id], now=now, force=True)


# ---------- One escrow ----------


def pay(escrow_id, *, run: PayoutRun | None = None, now=None, force: bool = False):
    """Make the next attempt for one escrow, or hold it. Returns (outcome, paise)."""
    now = now or timezone.now()
    with transaction.atomic():
        escrow = Escrow.objects.select_for_update().select_related("booking").get(pk=escrow_id)
        if escrow.status not in PAID_STATES or escrow.payout_status in UNDER_WAY:
            return "skipped", 0
        latest = escrow.payouts.order_by("-attempt").first()
        waiting = latest and (latest.next_attempt_at is None or latest.next_attempt_at > now)
        if latest and latest.status in (A.FAILED, A.REVERSED) and waiting and not force:
            return "skipped", 0  # backing off, or waiting for an admin
        talent_id = escrow.booking.talent_id
        account = PayoutAccount.objects.filter(talent_id=talent_id).first()
        if held := hold_reason(talent_id, account, now):
            status, reason = held
            if escrow.payout_status != status:
                escrow.payout_status = status
                escrow.save(update_fields=["payout_status", "updated_at"])
                if reason != "paused":
                    _notify(
                        "money.payout_on_hold",
                        escrow,
                        now,
                        key=reason,
                        reason=reason,
                        message=HOLD_MESSAGES[reason],
                    )
            return f"held:{reason}", 0
        try:
            payout = Payout.objects.create(
                escrow=escrow,
                talent_id=talent_id,
                run=run,
                attempt=(latest.attempt + 1) if latest else 1,
                amount_paise=escrow.payout_paise,
                fund_account_id=account.fund_account_id,
                account_display=account.display,
                created_at=now,
            )
        except IntegrityError:
            return "skipped", 0  # another run got there first
        escrow.payout_status = P.SENDING
        escrow.save(update_fields=["payout_status", "updated_at"])
    return _submit(payout.pk, account.method, now)


def _submit(payout_id, method: str, now) -> tuple[str, int]:
    payout = Payout.objects.select_related("escrow").get(pk=payout_id)
    try:
        result = get_provider().create_payout(
            fund_account_id=payout.fund_account_id,
            amount_paise=payout.amount_paise,
            method=method,
            idempotency_key=str(payout.pk),
            reference=str(payout.pk),
            narration="Barterly stipend",
        )
    except GatewayError as exc:
        fail(payout.pk, str(exc), now=now)
        return "failed", 0
    if result.status in FAILED_STATES:
        fail(payout.pk, result.reason or f"The provider said {result.status}.", now=now)
        return "failed", 0
    accept(
        payout.pk, provider_id=result.id, processed=result.status == DONE, utr=result.utr, now=now
    )
    return "sent", payout.amount_paise


def _resend_stuck(now) -> None:
    stuck = Payout.objects.filter(status=A.CREATING, created_at__lt=now - STUCK_AFTER)
    for payout in stuck.select_related("escrow__booking__talent__payout_account")[:100]:
        account = PayoutAccount.objects.filter(talent_id=payout.talent_id).first()
        _submit(payout.pk, account.method if account else "", now)


# ---------- Results ----------


def accept(payout_id, *, provider_id: str, processed: bool = False, utr: str = "", now=None):
    """The provider took the payout (and maybe already paid it)."""
    now = now or timezone.now()
    with transaction.atomic():
        payout = (
            Payout.objects.select_for_update().select_related("escrow__booking").get(pk=payout_id)
        )
        escrow = Escrow.objects.select_for_update().get(pk=payout.escrow_id)
        if payout.status == A.CREATING:
            ledger.post(
                "payout_sent",
                f"payout:{payout.pk}",
                [Line(TALENT, GATEWAY, payout.amount_paise)],
                booking=payout.escrow.booking,
                reference=provider_id,
                now=now,
            )
            before = snapshot(escrow, AUDIT)
            payout.status, payout.provider_payout_id = A.PROCESSING, provider_id
            escrow.payout_status, escrow.payout_transfer_id = P.SENT, provider_id
            log_action(
                actor=None,
                action="money.payout_sent",
                obj=escrow,
                before=before,
                after={
                    **snapshot(escrow, AUDIT),
                    "payout_id": str(payout.pk),
                    "provider_payout_id": provider_id,
                    "amount_paise": payout.amount_paise,
                },
            )
        if processed and payout.status == A.PROCESSING:
            before = snapshot(escrow, AUDIT)
            payout.status, payout.processed_at, payout.utr = A.PROCESSED, now, utr[:60]
            escrow.payout_status = P.SETTLED
            if escrow.status == EscrowStatus.RELEASED:
                escrow.status = EscrowStatus.PAID_OUT
            log_action(
                actor=None,
                action="money.payout_settled",
                obj=escrow,
                before=before,
                after={**snapshot(escrow, AUDIT), "payout_id": str(payout.pk), "utr": payout.utr},
            )
            _notify(
                "money.payout_paid",
                escrow,
                now,
                key=str(payout.pk),
                amount=_rupees(payout.amount_paise),
                account=payout.account_display,
            )
        payout.save()
        escrow.save()
    return payout


def fail(payout_id, reason: str, *, reversed_by_bank: bool = False, now=None) -> Payout:
    """The payout didn't happen (or the bank sent it back): undo it in the ledger and
    schedule the next attempt."""
    now = now or timezone.now()
    with transaction.atomic():
        payout = (
            Payout.objects.select_for_update().select_related("escrow__booking").get(pk=payout_id)
        )
        if payout.status in (A.FAILED, A.REVERSED):
            return payout
        escrow = Escrow.objects.select_for_update().get(pk=payout.escrow_id)
        if payout.status in (A.PROCESSING, A.PROCESSED):
            ledger.post(
                "payout_reversed",
                f"payout_reversed:{payout.pk}",
                [Line(GATEWAY, TALENT, payout.amount_paise)],
                booking=payout.escrow.booking,
                reference=payout.provider_payout_id,
                now=now,
            )
        before = snapshot(escrow, AUDIT)
        payout.status = A.REVERSED if reversed_by_bank else A.FAILED
        payout.failure_reason = (reason or "No reason given.")[:300]
        retries_left = (
            payout.attempt <= len(BACKOFF) and payout.attempt < settings.PAYOUT_MAX_ATTEMPTS
        )
        payout.next_attempt_at = now + BACKOFF[payout.attempt - 1] if retries_left else None
        payout.save()
        escrow.payout_status = P.FAILED
        if escrow.status == EscrowStatus.PAID_OUT:
            escrow.status = EscrowStatus.RELEASED
        escrow.save()
        log_action(
            actor=None,
            action="money.payout_failed",
            obj=escrow,
            before=before,
            after={
                **snapshot(escrow, AUDIT),
                "payout_id": str(payout.pk),
                "reason": payout.failure_reason,
                "attempt": payout.attempt,
                "next_attempt_at": payout.next_attempt_at,
            },
        )
        _notify(
            "money.payout_failed",
            escrow,
            now,
            key=str(payout.pk),
            amount=_rupees(payout.amount_paise),
            account=payout.account_display,
        )
        if payout.next_attempt_at is None:
            from apps.money import alerts

            alerts.raise_alert(
                "A payout failed on its last attempt",
                {"payout_id": str(payout.pk), "reason": payout.failure_reason},
                obj=payout,
            )
    return payout


def _rupees(paise: int) -> str:
    from decimal import Decimal

    return f"₹{Decimal(paise) / 100:,.2f}"


def _notify(name: str, escrow: Escrow, now, *, key: str, **extra) -> None:
    booking = escrow.booking
    publish(
        DomainEvent(
            name,
            {
                "booking_id": str(booking.pk),
                "escrow_id": str(escrow.pk),
                "talent_id": str(booking.talent_id),
                "gig_title": booking.gig.title,
                "dedup_key": f"{name}:{escrow.pk}:{key}",
                "notify": ["talent"],
                **extra,
            },
            occurred_at=now,
        )
    )


# ---------- Webhooks ----------


def handle_webhook(body: bytes, headers, now=None) -> str:
    """RazorpayX: payout.processed/reversed/failed/rejected and fund account
    validations. Signature checked; each event id applied once (GatewayEvent)."""
    from apps.money.models import GatewayEvent
    from apps.money.payout_accounts import on_validation_event

    data = get_provider().parse_webhook(body, headers)
    now = now or timezone.now()
    try:
        with transaction.atomic():
            record = GatewayEvent.objects.create(
                event_id=data.event_id, event=data.event, payload=data.raw, received_at=now
            )
            if data.event.startswith("fund_account.validation"):
                outcome = on_validation_event(data.validation, now)
            else:
                outcome = _payout_event(data.event, data.payout, now)
            record.outcome = outcome[:200]
            record.save(update_fields=["outcome"])
    except IntegrityError:
        if GatewayEvent.objects.filter(event_id=data.event_id).exists():
            return "duplicate"
        raise
    return outcome


def _payout_event(event: str, entity: dict, now) -> str:
    payout = Payout.objects.filter(pk=_uuid(entity.get("reference_id"))).first() or (
        Payout.objects.filter(provider_payout_id=entity.get("id") or "-").first()
    )
    if payout is None:
        return "not a Barterly payout"
    details = entity.get("status_details") or {}
    reason = details.get("description") or entity.get("failure_reason") or ""
    if event == "payout.processed":
        accept(
            payout.pk,
            provider_id=entity.get("id", ""),
            processed=True,
            utr=entity.get("utr") or "",
            now=now,
        )
        return "payout processed"
    if event == "payout.reversed":
        fail(payout.pk, reason or "The bank returned the payout.", reversed_by_bank=True, now=now)
        return "payout reversed"
    if event in ("payout.failed", "payout.rejected"):
        fail(payout.pk, reason or f"The provider said {event.split('.')[1]}.", now=now)
        return "payout failed"
    return "ignored"


def _uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None
