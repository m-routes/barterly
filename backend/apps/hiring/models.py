"""Vendor-side hiring data. Notes, tags and saved filters are private to the vendor:
no serializer an applicant can reach includes them."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel

MAX_TAGS = 10
MAX_SLOTS = 3


class ApplicationNote(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="private_notes"
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=2000)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Note on {self.application_id}"


class ApplicationTag(models.Model):
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="private_tags"
    )
    label = models.CharField(max_length=30)

    class Meta:
        ordering = ["label"]
        constraints = [
            models.UniqueConstraint(fields=["application", "label"], name="hiring_tag_unique")
        ]

    def __str__(self) -> str:
        return self.label


class SavedApplicantFilter(TimeStampedModel):
    """A vendor's named applicant-list filter (status, min_score, sort, tag), for one gig
    or all their gigs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applicant_filters"
    )
    gig = models.ForeignKey(
        "gigs.Gig", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(max_length=60)
    params = models.JSONField(default=dict)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["vendor", "name"], name="hiring_filter_name_unique")
        ]

    def __str__(self) -> str:
        return self.name


class InterviewStatus(models.TextChoices):
    PROPOSED = "proposed", "Waiting for the talent to pick a time"
    SCHEDULED = "scheduled", "Scheduled"
    NEW_TIMES_REQUESTED = "new_times_requested", "Talent asked for other times"
    CANCELLED = "cancelled", "Cancelled"


ACTIVE_INTERVIEW = [
    InterviewStatus.PROPOSED,
    InterviewStatus.SCHEDULED,
    InterviewStatus.NEW_TIMES_REQUESTED,
]


class Interview(TimeStampedModel):
    """One interview for an application. Times are stored in UTC (USE_TZ) and shown
    in Asia/Kolkata."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="interviews"
    )
    status = models.CharField(
        max_length=20, choices=InterviewStatus.choices, default=InterviewStatus.PROPOSED
    )
    video_link = models.URLField(max_length=300)
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    note = models.CharField(max_length=500, blank=True, help_text="Shown to the talent.")
    chosen_slot = models.ForeignKey(
        "InterviewSlot", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    starts_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="The picked slot's start (UTC)."
    )
    day_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    hour_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(status__in=ACTIVE_INTERVIEW),
                name="hiring_one_active_interview",
            ),
            models.CheckConstraint(
                condition=~Q(status="scheduled") | Q(starts_at__isnull=False),
                name="hiring_scheduled_has_time",
            ),
        ]

    def __str__(self) -> str:
        return f"Interview for {self.application_id} ({self.status})"


class InterviewSlot(models.Model):
    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="slots")
    starts_at = models.DateTimeField()

    class Meta:
        ordering = ["starts_at"]

    def __str__(self) -> str:
        return f"{self.starts_at:%Y-%m-%d %H:%M} UTC"
