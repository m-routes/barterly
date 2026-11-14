"""Verification records.

We keep only what we need to show and audit a decision: provider reference ids,
statuses and masked values (last four characters). Identity documents and selfies stay
with the KYC provider; a database constraint stops an ID document pointing at an upload.

Change statuses and badges through apps.verification.services, which audit-log them.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel
from apps.verification.constants import (
    MEDIA_DOCUMENT_TYPES,
    BadgeKind,
    CaseStatus,
    CheckType,
    DocumentStatus,
    DocumentType,
    SubjectType,
)


class VerificationCase(TimeStampedModel):
    """One check for one user (e.g. a vendor's property), across every attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="verification_cases"
    )
    check_type = models.CharField(max_length=30, choices=CheckType.choices)
    subject_type = models.CharField(max_length=20, choices=SubjectType.choices)
    subject_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="What was verified: a profile id for a property, 'instagram:<handle>', ...",
    )
    status = models.CharField(
        max_length=20, choices=CaseStatus.choices, default=CaseStatus.NOT_STARTED
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="verification_reviews",
        help_text="Admin who made the last decision. Empty for provider decisions.",
    )
    reason = models.TextField(
        blank=True,
        max_length=1000,
        help_text="Why it was rejected or what to change. Shown to the user.",
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Non-sensitive facts for the reviewer: pin, masked numbers, reference contact.",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "check_type"], name="verification_case_one_per_check"
            ),
            models.CheckConstraint(
                condition=Q(status__in=CaseStatus.values), name="verification_case_status_valid"
            ),
        ]
        indexes = [models.Index(fields=["status", "check_type", "submitted_at"])]

    def __str__(self) -> str:
        return f"{self.check_type} for {self.user_id}: {self.status}"


class VerificationDocument(TimeStampedModel):
    """One piece of evidence: a provider reference, a masked number, or an upload."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(VerificationCase, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    status = models.CharField(
        max_length=10, choices=DocumentStatus.choices, default=DocumentStatus.PENDING
    )
    provider = models.CharField(max_length=40, blank=True, help_text="KYC provider name.")
    provider_reference = models.CharField(
        max_length=128, blank=True, help_text="The provider's id for this check."
    )
    masked_value = models.CharField(
        max_length=4, blank=True, help_text="Last four characters of the number, nothing more."
    )
    media = models.ForeignKey(
        "media.MediaFile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="verification_documents",
        help_text="Our upload. Only property photos and certificates, never an ID.",
    )
    metadata = models.JSONField(
        default=dict, blank=True, help_text="E.g. a photo's location or a certificate's title."
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(media__isnull=True) | Q(document_type__in=sorted(MEDIA_DOCUMENT_TYPES)),
                name="verification_document_no_id_uploads",
                violation_error_message="Identity documents must stay with the KYC provider.",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_reference"],
                condition=~Q(provider_reference=""),
                name="verification_document_provider_ref_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_type} ({self.status})"


class Badge(TimeStampedModel):
    """A badge shown on a profile. Revoked badges stay as history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="badges"
    )
    kind = models.CharField(max_length=30, choices=BadgeKind.choices)
    case = models.ForeignKey(
        VerificationCase, null=True, blank=True, on_delete=models.PROTECT, related_name="badges"
    )
    granted_at = models.DateTimeField()
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Empty when granted by the system or the KYC provider.",
    )
    grant_reason = models.CharField(max_length=300)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revoke_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-granted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind"],
                condition=Q(revoked_at__isnull=True),
                name="verification_badge_one_active_per_kind",
            ),
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True) | ~Q(revoke_reason=""),
                name="verification_badge_revoke_has_reason",
            ),
        ]

    def __str__(self) -> str:
        state = "revoked" if self.revoked_at else "active"
        return f"{self.kind} for {self.user_id} ({state})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class KycWebhookEvent(models.Model):
    """Each webhook delivery we accepted, keyed by its idempotency key.

    No payload is stored: it can carry personal data. A repeat key is acknowledged
    and skipped.
    """

    provider = models.CharField(max_length=40)
    idempotency_key = models.CharField(max_length=128)
    provider_reference = models.CharField(max_length=128, blank=True)
    outcome = models.CharField(max_length=30, help_text="What we did with it.")
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "idempotency_key"], name="verification_webhook_once"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.idempotency_key} ({self.outcome})"
