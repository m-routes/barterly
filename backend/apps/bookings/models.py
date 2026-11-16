"""Bookings, their append-only event log, and the record of scheduled job runs.

Change a booking's status only through apps.bookings.services, which checks the one
transition table (lifecycle.TRANSITIONS), writes a BookingEvent and an AuditLog row,
and publishes a domain event.
"""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.bookings.lifecycle import Actor, BookingStatus
from apps.common.models import TimeStampedModel


class Booking(TimeStampedModel):
    """An engagement: created awaiting signatures when an offer is accepted, and
    confirmed when both sides have signed the agreement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        "applications.Application", on_delete=models.PROTECT, related_name="booking"
    )
    gig = models.ForeignKey("gigs.Gig", on_delete=models.PROTECT, related_name="bookings")
    talent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="talent_bookings"
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vendor_bookings"
    )
    status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.SIGNING
    )
    status_reason = models.CharField(max_length=500, blank=True)
    status_changed_at = models.DateTimeField(default=timezone.now)
    start_date = models.DateField()
    end_date = models.DateField()
    confirmed_at = models.DateTimeField(
        null=True, blank=True, help_text="When both sides had signed and the slot was taken."
    )
    checked_in_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["gig", "status"], name="booking_gig_status_idx"),
            models.Index(fields=["talent", "status"], name="booking_talent_idx"),
            models.Index(fields=["vendor", "status"], name="booking_vendor_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=BookingStatus.values), name="booking_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(end_date__gt=F("start_date")), name="booking_dates_in_order"
            ),
        ]

    def __str__(self) -> str:
        return f"Booking {self.pk} ({self.status})"


class BookingEvent(models.Model):
    """One status change of a booking. Append-only: a database trigger refuses UPDATE
    and DELETE (migration 0002), so not even the app's own database user can rewrite
    history."""

    id = models.BigAutoField(primary_key=True)
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="events")
    from_state = models.CharField(max_length=20)
    to_state = models.CharField(max_length=20)
    actor = models.CharField(max_length=10, choices=Actor.choices)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The person, when a person made the change.",
    )
    reason = models.TextField(blank=True, max_length=1000)
    metadata = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.booking_id}: {self.from_state} → {self.to_state}"


class JobRun(models.Model):
    """One run of a scheduled job, for checking the scheduler is doing its work."""

    id = models.BigAutoField(primary_key=True)
    job = models.CharField(max_length=50, db_index=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    error = models.TextField(blank=True)
    trigger = models.CharField(max_length=20, default="scheduler", help_text="scheduler or manual")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.job} at {self.started_at:%Y-%m-%d %H:%M}"


class CancelledBy(models.TextChoices):
    TALENT = "talent", "The talent"
    VENDOR = "vendor", "The host"
    SYSTEM = "system", "Barterly, automatically"
    ADMIN = "admin", "Barterly admin"


class CancellationReason(models.TextChoices):
    # Either side.
    EMERGENCY = "emergency", "A personal or family emergency"
    SAFETY = "safety", "A safety or conduct concern"
    PLANS_CHANGED = "plans_changed", "Plans changed"
    OTHER = "other", "Something else"
    # The talent.
    ILLNESS = "illness", "Illness or injury"
    TRAVEL = "travel", "Travel disruption"
    OTHER_WORK = "other_work", "Took up other work"
    # The host.
    PROPERTY_UNAVAILABLE = "property_unavailable", "The property can't host (repairs, closure)"
    STAFFING = "staffing", "Staffing needs changed"
    # Barterly.
    SLOTS_FILLED = "slots_filled", "Every place was filled before both sides signed"
    NOT_SIGNED = "not_signed", "Not signed by both before the stay started"
    ADMIN = "admin", "Cancelled by Barterly support"


R = CancellationReason
REASONS_FOR: dict[str, tuple[str, ...]] = {
    CancelledBy.TALENT: (
        R.ILLNESS,
        R.EMERGENCY,
        R.TRAVEL,
        R.OTHER_WORK,
        R.PLANS_CHANGED,
        R.SAFETY,
        R.OTHER,
    ),
    CancelledBy.VENDOR: (
        R.PROPERTY_UNAVAILABLE,
        R.STAFFING,
        R.EMERGENCY,
        R.PLANS_CHANGED,
        R.SAFETY,
        R.OTHER,
    ),
    CancelledBy.SYSTEM: (R.SLOTS_FILLED, R.NOT_SIGNED),
    CancelledBy.ADMIN: (R.ADMIN,),
}


class CancellationEffect(models.TextChoices):
    """What a cancellation does to the canceller's reliability (apps.reliability)."""

    NONE = "none", "No effect (not yet confirmed, or not cancelled by either side)"
    FREE = "free", "Free: before the policy's notice period"
    LATE = "late", "Late: inside the policy's notice period"
    LAST_MINUTE = "last_minute", "Last minute: a day or less before the stay"


class Cancellation(models.Model):
    """Why and when a booking was cancelled, and what that did to reliability.

    One per booking. Written with the booking's move to cancelled, in the same
    transaction, by apps.bookings.cancellation only."""

    id = models.BigAutoField(primary_key=True)
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="cancellation")
    by = models.CharField(max_length=10, choices=CancelledBy.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    reason = models.CharField(max_length=30, choices=CancellationReason.choices)
    note = models.TextField(max_length=1000, blank=True)
    was_status = models.CharField(
        max_length=20, help_text="signing or confirmed: the status it was cancelled from."
    )
    policy = models.CharField(max_length=10, blank=True, help_text="The agreement's policy.")
    notice_days = models.PositiveSmallIntegerField(null=True, blank=True)
    days_before_start = models.IntegerField()
    effect = models.CharField(max_length=12, choices=CancellationEffect.choices)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(by__in=CancelledBy.values), name="cancellation_by_valid"
            ),
            models.CheckConstraint(
                condition=Q(reason__in=CancellationReason.values),
                name="cancellation_reason_valid",
            ),
            models.CheckConstraint(
                condition=Q(effect__in=CancellationEffect.values),
                name="cancellation_effect_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.booking_id} cancelled by {self.by} ({self.reason}, {self.effect})"
