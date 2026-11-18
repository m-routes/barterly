"""Billing: plans as data, each vendor's subscription, coupons, gateway webhook events
and GST invoices.

Change a subscription's status only through apps.billing.services (audited), and issue
invoices only through apps.billing.invoices (sequential numbers, one per payment).
"""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone

FEATURES = ("talent_search", "agreements", "ai_fit_scores", "team_roles")


class Plan(models.Model):
    """A plan vendors can subscribe to. Seeded by migration 0002; edit in admin."""

    code = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=40)
    description = models.CharField(max_length=200, blank=True)
    price_paise = models.PositiveIntegerField(help_text="Per month, before GST, in paise.")
    currency = models.CharField(max_length=3, default="INR")
    max_live_gigs = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Empty: no limit."
    )
    features = models.JSONField(
        default=dict, blank=True, help_text=f"Feature flags: {', '.join(FEATURES)}."
    )
    gateway_plan_id = models.CharField(
        max_length=60,
        blank=True,
        help_text="The plan's id at Razorpay (created in its dashboard, price incl. GST).",
    )
    is_public = models.BooleanField(default=True, help_text="Offered to vendors.")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "price_paise"]

    def __str__(self) -> str:
        return self.name

    def has(self, flag: str) -> bool:
        return bool(self.features.get(flag))


class Coupon(models.Model):
    """A code that gives a free trial before the first charge (the launch cohort)."""

    code = models.CharField(max_length=30, unique=True)
    trial_days = models.PositiveSmallIntegerField(default=90)
    max_redemptions = models.PositiveIntegerField(null=True, blank=True)
    redemptions = models.PositiveIntegerField(default=0, editable=False)
    valid_until = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self) -> str:
        return self.code

    def usable(self, now) -> bool:
        if not self.active or (self.valid_until and self.valid_until < now):
            return False
        return self.max_redemptions is None or self.redemptions < self.max_redemptions


class SubscriptionStatus(models.TextChoices):
    CREATED = "created", "Waiting for checkout"
    AUTHENTICATED = "authenticated", "Card set up (trial or first charge pending)"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Payment failed: retrying"
    HALTED = "halted", "Retries exhausted"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


# A vendor has at most one subscription in these states.
OPEN_STATUSES = (
    SubscriptionStatus.CREATED,
    SubscriptionStatus.AUTHENTICATED,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAST_DUE,
    SubscriptionStatus.HALTED,
)


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscriptions"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    pending_plan = models.ForeignKey(
        Plan,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="A downgrade that takes effect at the end of the current period.",
    )
    status = models.CharField(
        max_length=15, choices=SubscriptionStatus.choices, default=SubscriptionStatus.CREATED
    )
    gateway = models.CharField(max_length=20, default="razorpay")
    gateway_subscription_id = models.CharField(max_length=60, unique=True)
    checkout_url = models.URLField(max_length=300, blank=True)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.PROTECT)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    payment_failed_at = models.DateTimeField(
        null=True, blank=True, help_text="First failure of the current dunning run."
    )
    grace_until = models.DateTimeField(
        null=True, blank=True, help_text="Paid features stay on until here while retrying."
    )
    reminders_sent = models.PositiveSmallIntegerField(default=0)
    cancel_at_period_end = models.BooleanField(default=False)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor"],
                condition=Q(status__in=[s.value for s in OPEN_STATUSES]),
                name="billing_one_open_subscription",
            ),
            models.CheckConstraint(
                condition=Q(status__in=SubscriptionStatus.values),
                name="billing_subscription_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.vendor_id} on {self.plan_id} ({self.status})"


class WebhookEvent(models.Model):
    """Every gateway webhook received, once. The gateway's event id makes handling
    idempotent: a repeat delivery is recorded as a duplicate and does nothing."""

    id = models.BigAutoField(primary_key=True)
    gateway = models.CharField(max_length=20, default="razorpay")
    event_id = models.CharField(max_length=80)
    event = models.CharField(max_length=60)
    payload = models.JSONField(encoder=DjangoJSONEncoder)
    received_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(fields=["gateway", "event_id"], name="billing_event_once"),
        ]

    def __str__(self) -> str:
        return f"{self.event} ({self.event_id})"


class InvoiceCounter(models.Model):
    """The last invoice number used in a financial year (gap-free, under a row lock)."""

    financial_year = models.CharField(max_length=7, primary_key=True)  # "2026-27"
    last = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.financial_year}: {self.last}"


class Invoice(models.Model):
    """A GST tax invoice for one charge. Amounts are in paise; the buyer and supplier
    details are copied at issue, so later profile edits don't change past invoices."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=30, unique=True)
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invoices"
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name="invoices"
    )
    gateway_payment_id = models.CharField(max_length=60, unique=True)
    plan_name = models.CharField(max_length=40)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    # The tax breakup.
    taxable_paise = models.PositiveIntegerField()
    cgst_paise = models.PositiveIntegerField(default=0)
    sgst_paise = models.PositiveIntegerField(default=0)
    igst_paise = models.PositiveIntegerField(default=0)
    total_paise = models.PositiveIntegerField()
    gst_rate_percent = models.DecimalField(max_digits=4, decimal_places=2)
    sac_code = models.CharField(max_length=8)
    place_of_supply = models.CharField(max_length=80)
    # The parties, as they were.
    supplier = models.JSONField(encoder=DjangoJSONEncoder)
    buyer_name = models.CharField(max_length=150)
    buyer_gstin = models.CharField(max_length=15, blank=True)
    buyer_address = models.TextField(blank=True)
    buyer_state = models.CharField(max_length=80, blank=True)
    buyer_email = models.EmailField(blank=True)
    # The document.
    pdf_key = models.CharField(max_length=300, blank=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    issued_at = models.DateTimeField(default=timezone.now)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    total_paise=models.F("taxable_paise")
                    + models.F("cgst_paise")
                    + models.F("sgst_paise")
                    + models.F("igst_paise")
                ),
                name="billing_invoice_adds_up",
            ),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def tax_paise(self) -> int:
        return self.cgst_paise + self.sgst_paise + self.igst_paise
