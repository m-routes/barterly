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
    """A confirmed engagement: created when the talent accepts an offer."""

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
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.CONFIRMED
    )
    status_reason = models.CharField(max_length=500, blank=True)
    status_changed_at = models.DateTimeField(default=timezone.now)
    start_date = models.DateField()
    end_date = models.DateField()
    confirmed_at = models.DateTimeField(default=timezone.now)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-confirmed_at"]
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
