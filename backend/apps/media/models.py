"""Uploaded files. The bytes live in the private media bucket; this is the record."""

import uuid

from django.conf import settings
from django.db import models

from apps.common.models import SoftDeleteModel, TimeStampedModel
from apps.media.policy import Kind


class MediaStatus(models.TextChoices):
    PENDING_UPLOAD = "pending_upload", "Waiting for upload"
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"
    REJECTED = "rejected", "Rejected"
    QUARANTINED = "quarantined", "Quarantined"


class ScanStatus(models.TextChoices):
    PENDING = "pending", "Not scanned yet"
    CLEAN = "clean", "Clean"
    INFECTED = "infected", "Infected"
    SKIPPED = "skipped", "No scanner configured"
    ERROR = "error", "Scan failed"


class MediaFile(TimeStampedModel, SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="media_files"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(
        max_length=20, choices=MediaStatus.choices, default=MediaStatus.PENDING_UPLOAD
    )
    content_type = models.CharField(max_length=50)
    size_bytes = models.BigIntegerField(help_text="Declared at upload, checked on confirm.")
    checksum_md5 = models.CharField(
        max_length=32, blank=True, help_text="Hex MD5 of the stored bytes (from Cloud Storage)."
    )
    object_key = models.CharField(max_length=300, unique=True)
    variants = models.JSONField(
        default=dict, blank=True, help_text='Resized copies, e.g. {"thumb": "<object key>"}'
    )
    scan_status = models.CharField(
        max_length=20, choices=ScanStatus.choices, default=ScanStatus.PENDING
    )
    scanned_at = models.DateTimeField(null=True, blank=True)
    upload_expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(size_bytes__gt=0), name="media_mediafile_size_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.id}"
