"""The money core: a double-entry ledger, escrow for paid and hybrid bookings,
deliverable submissions that release it, gateway events, reconciliation runs and the
kill switch.

Rules (see docs/money.md):
- Amounts are whole paise in integer columns. No floats anywhere.
- Money moves only through apps.money.ledger.post(): one LedgerTransaction with an
  idempotency key, made of LedgerEntry lines that each debit one account and credit
  another for the same amount, so every movement balances by construction.
- Ledger rows are append-only: database triggers refuse UPDATE and DELETE (migration
  0002). A mistake is corrected by a new, reversing transaction.
"""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class AccountKind(models.TextChoices):
    ASSET = "asset", "Asset"
    LIABILITY = "liability", "Liability"
    REVENUE = "revenue", "Revenue"
    EXPENSE = "expense", "Expense"
    EQUITY = "equity", "Equity"


class Account(models.Model):
    """A ledger account (seeded by migration 0003). Balances are computed from entries:
    debits minus credits for assets and expenses, the reverse for the others."""

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=AccountKind.choices)
    currency = models.CharField(max_length=3, default="INR")

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class LedgerTransaction(models.Model):
    """One money movement. The idempotency key makes posting it twice a no-op."""

    id = models.BigAutoField(primary_key=True)
    idempotency_key = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=40, db_index=True)
    booking = models.ForeignKey(
        "bookings.Booking",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_transactions",
    )
    reference = models.CharField(
        max_length=120, blank=True, help_text="The gateway's id (payment, refund, transfer)."
    )
    memo = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.kind} {self.idempotency_key}"


class LedgerEntry(models.Model):
    """One line: `amount_paise` moves into `debit_account` out of `credit_account`."""

    id = models.BigAutoField(primary_key=True)
    transaction = models.ForeignKey(
        LedgerTransaction, on_delete=models.PROTECT, related_name="entries"
    )
    line = models.PositiveSmallIntegerField()
    debit_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    credit_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="+")
    amount_paise = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="INR")
    reference = models.CharField(max_length=120, blank=True)
    booking = models.ForeignKey(
        "bookings.Booking",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    idempotency_key = models.CharField(max_length=130, unique=True)  # <txn key>#<line>
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount_paise__gt=0), name="ledger_amount_positive"),
            models.CheckConstraint(
                condition=~Q(debit_account=F("credit_account")), name="ledger_two_accounts"
            ),
            models.UniqueConstraint(fields=["transaction", "line"], name="ledger_one_line"),
        ]

    def __str__(self) -> str:
        return f"{self.amount_paise}p {self.credit_account_id}→{self.debit_account_id}"


class EscrowStatus(models.TextChoices):
    AWAITING_FUNDING = "awaiting_funding", "Waiting for the host to fund"
    FUNDING = "funding", "Payment started"
    HELD = "held", "Funded and held"
    RELEASED = "released", "Released (payout to follow)"
    PAID_OUT = "paid_out", "Paid out"
    REFUNDED = "refunded", "Refunded"
    SPLIT = "split", "Split by an admin"


class PayoutStatus(models.TextChoices):
    """Where the escrow's payout stands (its latest Payout attempt, or why there's none)."""

    NONE = "", "No payout"
    WAITING_FOR_ACCOUNT = "waiting_for_account", "Waiting for a verified payout account"
    ON_HOLD = "on_hold", "On hold (ID check or a recent account change)"
    PAUSED = "paused", "Paused by the kill switch"
    SENDING = "sending", "Payout being created"
    SENT = "sent", "With the payout provider"
    SETTLED = "settled", "Paid out"
    FAILED = "failed", "Payout failed"


class Escrow(models.Model):
    """The stipend for one paid or hybrid booking, from funding to payout."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.PROTECT, related_name="escrow"
    )
    status = models.CharField(
        max_length=20, choices=EscrowStatus.choices, default=EscrowStatus.AWAITING_FUNDING
    )
    stipend_paise = models.BigIntegerField()
    fee_paise = models.BigIntegerField(help_text="Gateway fee charged to the host.")
    fee_gst_paise = models.BigIntegerField()
    total_paise = models.BigIntegerField(help_text="What the host pays.")
    gateway_order_id = models.CharField(max_length=60, blank=True, db_index=True)
    gateway_payment_id = models.CharField(max_length=60, blank=True)
    funded_at = models.DateTimeField(null=True, blank=True)
    frozen = models.BooleanField(default=False, help_text="A dispute: no release.")
    frozen_reason = models.CharField(max_length=300, blank=True)
    # The release, once decided.
    released_paise = models.BigIntegerField(default=0, help_text="Stipend released to talent.")
    commission_paise = models.BigIntegerField(default=0)
    commission_gst_paise = models.BigIntegerField(default=0)
    tds_paise = models.BigIntegerField(default=0)
    payout_paise = models.BigIntegerField(default=0)
    refund_paise = models.BigIntegerField(default=0)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.CharField(max_length=10, blank=True)  # vendor, system, admin
    payout_status = models.CharField(
        max_length=20, choices=PayoutStatus.choices, default=PayoutStatus.NONE, blank=True
    )
    payout_transfer_id = models.CharField(max_length=60, blank=True)
    refund_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(stipend_paise__gt=0)
                & Q(fee_paise__gte=0)
                & Q(fee_gst_paise__gte=0)
                & Q(total_paise=F("stipend_paise") + F("fee_paise") + F("fee_gst_paise")),
                name="escrow_amounts_add_up",
            ),
            models.CheckConstraint(
                condition=Q(released_paise__gte=0)
                & Q(refund_paise__gte=0)
                & Q(released_paise__lte=F("stipend_paise") - F("refund_paise")),
                name="escrow_never_overpays",
            ),
            models.CheckConstraint(
                condition=Q(
                    payout_paise=F("released_paise")
                    - F("commission_paise")
                    - F("commission_gst_paise")
                    - F("tds_paise")
                ),
                name="escrow_payout_adds_up",
            ),
            models.CheckConstraint(
                condition=Q(status__in=EscrowStatus.values), name="escrow_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"Escrow {self.booking_id} ({self.status})"

    @property
    def unreleased_paise(self) -> int:
        return self.stipend_paise - self.released_paise - self.refund_paise


class PayoutMethod(models.TextChoices):
    UPI = "upi", "UPI"
    BANK = "bank", "Bank account"


class ValidationStatus(models.TextChoices):
    NONE = "", "Not linked"
    PENDING = "pending", "Being checked"
    VERIFIED = "verified", "Verified"
    FAILED = "failed", "Couldn't be verified"


class PayoutAccount(models.Model):
    """Where a talent's payouts go: a UPI id or a bank account, held at the payout
    provider as a fund account. Only the provider's ids and a masked display are stored,
    never the full account number or UPI id. Payouts need it verified by the provider
    (an account validation), and are held for PAYOUT_ACCOUNT_CHANGE_HOLD_HOURS after a
    change (apps.money.payout_accounts)."""

    talent = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payout_account"
    )
    # Unused since payouts moved to fund accounts; dropped in a later migration.
    gateway_account_id = models.CharField(max_length=60, unique=True, null=True, blank=True)
    active = models.BooleanField(default=False, help_text="Verified: payouts can go here.")
    pan_on_file = models.BooleanField(
        default=False, help_text="Decides the TDS rate (no PAN: the higher rate)."
    )
    method = models.CharField(max_length=4, choices=PayoutMethod.choices, blank=True)
    display = models.CharField(max_length=80, blank=True, help_text="Masked, for showing.")
    provider_contact_id = models.CharField(max_length=60, blank=True)
    fund_account_id = models.CharField(max_length=60, blank=True, db_index=True)
    validation_status = models.CharField(
        max_length=10, choices=ValidationStatus.choices, default=ValidationStatus.NONE, blank=True
    )
    validation_id = models.CharField(max_length=60, blank=True, db_index=True)
    validation_reason = models.CharField(max_length=200, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    changed_at = models.DateTimeField(null=True, blank=True, help_text="Last replaced.")
    hold_until = models.DateTimeField(
        null=True, blank=True, help_text="No payouts before this (set by a change)."
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.talent_id}: {self.display or self.gateway_account_id}"


class SubmissionReview(models.TextChoices):
    PENDING = "", "Waiting for the host"
    APPROVED = "approved", "Approved"
    CHANGES = "changes", "Changes asked for"


class DeliverableSubmission(models.Model):
    """Work the talent hands in (links to posts, photos, notes). The host approves it,
    which releases the escrow, or asks for changes. No answer for
    ESCROW_AUTO_RELEASE_HOURS after the latest one releases it automatically."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, related_name="submissions"
    )
    note = models.TextField(max_length=2000, blank=True)
    links = models.JSONField(default=list, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    review = models.CharField(
        max_length=10,
        choices=SubmissionReview.choices,
        default=SubmissionReview.PENDING,
        blank=True,
    )
    review_note = models.TextField(max_length=1000, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"Submission {self.booking_id} at {self.submitted_at:%Y-%m-%d}"


class GatewayEvent(models.Model):
    """Every escrow webhook, once (the event id makes handling idempotent)."""

    id = models.BigAutoField(primary_key=True)
    event_id = models.CharField(max_length=80, unique=True)
    event = models.CharField(max_length=60)
    payload = models.JSONField(encoder=DjangoJSONEncoder)
    received_at = models.DateTimeField(default=timezone.now)
    outcome = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"{self.event} ({self.event_id})"


class ReconciliationRun(models.Model):
    """One day's comparison of ledger totals with the gateway's."""

    id = models.BigAutoField(primary_key=True)
    day = models.DateField(unique=True)
    ledger = models.JSONField(encoder=DjangoJSONEncoder)
    gateway = models.JSONField(encoder=DjangoJSONEncoder)
    mismatches = models.JSONField(default=list, encoder=DjangoJSONEncoder)
    ok = models.BooleanField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day}: {'ok' if self.ok else 'MISMATCH'}"


class EscrowControl(models.Model):
    """The runtime kill switch (one row). Paused here or by settings.ESCROW_PAUSED,
    new funding and all payouts stop; webhooks are still recorded."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    paused = models.BooleanField(default=False)
    reason = models.CharField(max_length=300, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    changed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="escrow_control_one_row")]
        permissions = [
            ("decide_escrow", "Can release, split or refund a held escrow"),
            ("toggle_kill_switch", "Can pause and resume escrow funding and payouts"),
            ("run_payouts", "Can start payout runs and retry failed payouts"),
        ]

    def __str__(self) -> str:
        return "Paused" if self.paused else "Running"


class PayoutTrigger(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    RELEASE = "release", "After a release"
    ON_DEMAND = "on_demand", "Asked for by the talent"
    ADMIN = "admin", "Started by an admin"


class PayoutRun(models.Model):
    """One pass over the payouts owed: what was sent, held back (and why) or failed."""

    id = models.BigAutoField(primary_key=True)
    trigger = models.CharField(max_length=10, choices=PayoutTrigger.choices)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    talent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Only this talent's payouts (on demand).",
    )
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    considered = models.PositiveIntegerField(default=0)
    sent = models.PositiveIntegerField(default=0)
    held = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    sent_paise = models.BigIntegerField(default=0)
    held_reasons = models.JSONField(default=dict, blank=True, help_text="reason: count")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Payout run {self.pk} ({self.trigger})"


class PayoutAttemptStatus(models.TextChoices):
    CREATING = "creating", "Being created"
    PROCESSING = "processing", "With the provider"
    PROCESSED = "processed", "Paid out"
    FAILED = "failed", "Failed"
    REVERSED = "reversed", "Reversed by the bank"


LIVE_PAYOUT = ("creating", "processing", "processed")


class Payout(models.Model):
    """One attempt to pay an escrow's payout to the talent. The provider's idempotency
    key is this row's id, so retrying the same attempt can never pay twice; a failed
    attempt is followed by a new one."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    escrow = models.ForeignKey(Escrow, on_delete=models.PROTECT, related_name="payouts")
    talent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payouts"
    )
    run = models.ForeignKey(
        PayoutRun, null=True, blank=True, on_delete=models.PROTECT, related_name="payouts"
    )
    attempt = models.PositiveSmallIntegerField()
    amount_paise = models.BigIntegerField()
    fund_account_id = models.CharField(max_length=60)
    account_display = models.CharField(max_length=80)
    status = models.CharField(
        max_length=10, choices=PayoutAttemptStatus.choices, default=PayoutAttemptStatus.CREATING
    )
    provider_payout_id = models.CharField(max_length=60, blank=True, db_index=True)
    utr = models.CharField(max_length=60, blank=True, help_text="The bank's reference.")
    failure_reason = models.CharField(max_length=300, blank=True)
    next_attempt_at = models.DateTimeField(
        null=True, blank=True, help_text="When a failed payout is tried again; empty: an admin."
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount_paise__gt=0), name="payout_amount_positive"),
            models.UniqueConstraint(fields=["escrow", "attempt"], name="payout_one_per_attempt"),
            # Never two payouts of one escrow in flight or paid.
            models.UniqueConstraint(
                fields=["escrow"],
                condition=Q(status__in=LIVE_PAYOUT),
                name="payout_one_live_per_escrow",
            ),
        ]

    def __str__(self) -> str:
        return f"Payout {self.amount_paise}p to {self.talent_id} ({self.status})"
