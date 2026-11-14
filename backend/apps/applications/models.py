"""Talent applying to gigs. Change statuses only through apps.applications.services."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.applications.constants import ACTIVE, ApplicationStatus
from apps.common.models import TimeStampedModel


class Application(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gig = models.ForeignKey("gigs.Gig", on_delete=models.PROTECT, related_name="applications")
    talent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applications"
    )
    pitch = models.TextField(max_length=2000)
    answers = models.JSONField(
        default=list,
        blank=True,
        help_text="Answers to the gig's screening questions, in order.",
    )
    proposed_start = models.DateField()
    proposed_end = models.DateField()
    status = models.CharField(
        max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.APPLIED
    )
    status_reason = models.CharField(max_length=500, blank=True)
    fit_score = models.PositiveSmallIntegerField(help_text="Fit score when the talent applied.")
    fit_breakdown = models.JSONField(help_text="The score's breakdown when the talent applied.")
    applied_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-applied_at"]
        indexes = [
            models.Index(fields=["gig", "status", "fit_score"], name="application_gig_fit_idx"),
            models.Index(fields=["talent", "status"], name="application_talent_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["gig", "talent"],
                condition=Q(status__in=sorted(ACTIVE)),
                name="application_one_active_per_gig",
                violation_error_message="You already have an active application for this gig.",
            ),
            models.CheckConstraint(
                condition=Q(proposed_end__gt=models.F("proposed_start")),
                name="application_dates_in_order",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ApplicationStatus.values), name="application_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.talent_id} → {self.gig_id} ({self.status})"


class AttachmentKind(models.TextChoices):
    PHOTO = "photo", "Photo"
    VIDEO = "video", "Video"
    DOCUMENT = "document", "Document"
    LINK = "link", "Link"


class ApplicationAttachment(models.Model):
    """One of the talent's uploads, or a link (portfolio, reel, CV)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="attachments"
    )
    kind = models.CharField(max_length=10, choices=AttachmentKind.choices)
    media = models.ForeignKey(
        "media.MediaFile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="application_attachments",
    )
    url = models.URLField(max_length=500, blank=True)
    title = models.CharField(max_length=120, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(kind=AttachmentKind.LINK) & Q(media__isnull=True) & ~Q(url=""))
                | (~Q(kind=AttachmentKind.LINK) & Q(media__isnull=False) & Q(url="")),
                name="application_attachment_media_or_link",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} on {self.application_id}"
