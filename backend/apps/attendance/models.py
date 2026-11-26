"""Attendance: check-in passes, check-ins (and check-outs), and volunteer hour logs."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class AttendancePass(models.Model):
    """What the talent shows at arrival: a signed QR token naming this pass, and a
    six-digit code from `code_secret` (a fallback when scanning fails). The talent's
    location when they opened it gives the check-in its distance from the property."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, related_name="attendance_passes"
    )
    talent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    issued_at = models.DateTimeField(default=timezone.now)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    code_secret = models.CharField(max_length=64, help_text="Base32 TOTP secret for the code.")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    located_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_until__gt=models.F("valid_from")), name="attendance_pass_window"
            )
        ]

    def __str__(self) -> str:
        return f"Pass {self.pk} for {self.booking_id}"


class CheckInMethod(models.TextChoices):
    QR = "qr", "QR scanned"
    CODE = "code", "Six-digit code"
    MANUAL = "manual", "Confirmed by hand"
    OTHER = "other", "Booking status changed directly"


class FlagReason(models.TextChoices):
    NONE = "", "Not flagged"
    FAR = "far", "Far from the property"


class CheckIn(models.Model):
    """A booking's arrival (and departure). `checked_in_at` is when the host scanned or
    confirmed it, which may be earlier than `recorded_at` when it was queued offline."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.PROTECT, related_name="attendance"
    )
    method = models.CharField(max_length=10, choices=CheckInMethod.choices)
    attendance_pass = models.ForeignKey(
        AttendancePass, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    client_id = models.UUIDField(
        null=True, blank=True, unique=True, help_text="The device's id: a re-sync applies once."
    )
    checked_in_at = models.DateTimeField()
    recorded_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.CharField(max_length=300, blank=True, help_text="For a manual check-in.")
    distance_m = models.PositiveIntegerField(
        null=True, blank=True, help_text="The talent's distance from the property, if known."
    )
    location_age_minutes = models.PositiveIntegerField(null=True, blank=True)
    flag = models.CharField(max_length=10, choices=FlagReason.choices, blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    review_note = models.CharField(max_length=300, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-checked_in_at"]

    def __str__(self) -> str:
        return f"Check-in {self.booking_id} ({self.method})"


class HourStatus(models.TextChoices):
    PENDING = "pending", "Waiting for the host"
    CONFIRMED = "confirmed", "Confirmed"
    DISPUTED = "disputed", "Disputed"


class HourLog(models.Model):
    """Hours a talent worked on one day of a stay. The host confirms or disputes it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, related_name="hour_logs"
    )
    talent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    day = models.DateField()
    minutes = models.PositiveSmallIntegerField()
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=HourStatus.choices, default=HourStatus.PENDING)
    vendor_note = models.CharField(max_length=300, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-day"]
        constraints = [
            models.UniqueConstraint(fields=["booking", "day"], name="attendance_one_log_per_day"),
            models.CheckConstraint(
                condition=Q(minutes__gt=0) & Q(minutes__lte=24 * 60),
                name="attendance_minutes_range",
            ),
        ]
        permissions = [("review_checkin", "Can review flagged check-ins")]

    def __str__(self) -> str:
        return f"{self.minutes} min on {self.day} for {self.booking_id}"
