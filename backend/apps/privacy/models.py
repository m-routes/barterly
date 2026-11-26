"""Consent records, data-rights requests and minor cases (docs/privacy.md).

A consent record is never edited: giving and withdrawing each add a row, and the newest
row per purpose is the person's current choice. Every change is also audit-logged.
"""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone

USER = settings.AUTH_USER_MODEL


class Purpose(models.TextChoices):
    TERMS = "terms", "Terms of service"
    PRIVACY = "privacy", "Privacy policy"
    LOCATION = "location", "Location use"
    SOCIAL = "social", "Social account access"
    MARKETING = "marketing", "Marketing messages"
    ANALYTICS = "analytics", "Product analytics"


# Needed to use Barterly at all. Withdrawing them means closing the account.
REQUIRED_PURPOSES = frozenset({Purpose.TERMS, Purpose.PRIVACY})


class ConsentSource(models.TextChoices):
    WEB = "web", "Web"
    MOBILE = "mobile", "Mobile app"
    API = "api", "API"
    SYSTEM = "system", "System"


# What a client says it is when it records consent ("system" is ours only).
CLIENT_SOURCES = [
    (ConsentSource.WEB.value, ConsentSource.WEB.label),
    (ConsentSource.MOBILE.value, ConsentSource.MOBILE.label),
    (ConsentSource.API.value, ConsentSource.API.label),
]


class ConsentRecordQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("Consent records are append-only")


class ConsentRecord(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="consent_records")
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    granted = models.BooleanField(help_text="True when given, False when withdrawn.")
    version = models.CharField(max_length=40, help_text="The document version shown.")
    source = models.CharField(max_length=10, choices=ConsentSource.choices)
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = ConsentRecordQuerySet.as_manager()

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "purpose", "-recorded_at"], name="privacy_consent_user_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(purpose__in=Purpose.values), name="privacy_consent_purpose_valid"
            )
        ]

    def __str__(self) -> str:
        verb = "gave" if self.granted else "withdrew"
        return f"{self.user_id} {verb} {self.purpose} v{self.version}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Consent records are append-only")
        super().save(*args, **kwargs)


class ExportStatus(models.TextChoices):
    READY = "ready", "Ready to download"
    EXPIRED = "expired", "Expired and deleted"


class DataExport(models.Model):
    """One JSON copy of a person's data, kept briefly in the media bucket."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="data_exports")
    status = models.CharField(max_length=10, choices=ExportStatus.choices)
    object_key = models.CharField(max_length=300, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Export {self.pk} ({self.status})"


class DeletionStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


class DeletionRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="deletion_requests")
    status = models.CharField(max_length=10, choices=DeletionStatus.choices)
    reason = models.CharField(max_length=500, blank=True)
    requested_at = models.DateTimeField(default=timezone.now)
    scheduled_for = models.DateTimeField(db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(
        default=dict, blank=True, encoder=DjangoJSONEncoder, help_text="Counts per step."
    )

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="scheduled"),
                name="privacy_one_scheduled_deletion",
            )
        ]

    def __str__(self) -> str:
        return f"Deletion of {self.user_id} ({self.status})"


class CorrectionStatus(models.TextChoices):
    OPEN = "open", "Open"
    DONE = "done", "Corrected"
    REJECTED = "rejected", "Not changed"


class CorrectionRequest(models.Model):
    """A correction people can't make themselves (e.g. their phone, or a signed record)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="correction_requests")
    field = models.CharField(max_length=60, help_text="What is wrong, e.g. 'phone'.")
    correct_value = models.CharField(max_length=500)
    note = models.TextField(max_length=1000, blank=True)
    status = models.CharField(
        max_length=10, choices=CorrectionStatus.choices, default=CorrectionStatus.OPEN
    )
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolution_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Correction of {self.field} for {self.user_id} ({self.status})"


class MinorSource(models.TextChoices):
    PROFILE_DOB = "profile_dob", "Date of birth entered under 18"
    REPORT = "report", "Reported by someone"
    STAFF = "staff", "Found by staff"


class MinorStatus(models.TextChoices):
    OPEN = "open", "Suspended, waiting for the trust team"
    CONFIRMED = "confirmed", "Confirmed minor: data purged"
    CLEARED = "cleared", "Adult after all: suspension lifted"


class MinorCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="minor_cases")
    source = models.CharField(max_length=20, choices=MinorSource.choices)
    status = models.CharField(max_length=10, choices=MinorStatus.choices)
    note = models.CharField(max_length=500, blank=True)
    restriction = models.CharField(
        max_length=80, blank=True, help_text="How the account was stopped: a suspension id."
    )
    detected_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-detected_at"]
        permissions = [("decide_minor_case", "Can confirm or clear a suspected minor")]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=Q(status="open"), name="privacy_one_open_minor_case"
            )
        ]

    def __str__(self) -> str:
        return f"Minor case for {self.user_id} ({self.status})"
