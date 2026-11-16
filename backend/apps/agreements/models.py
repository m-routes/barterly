"""Agreements: the signed record of a booking's terms, with every version kept.

An Agreement belongs to one booking. Each AgreementVersion is a frozen copy of the terms
and the PDF drawn up from them (stored in Cloud Storage, with its SHA-256). A version is
in force only once both sides have signed it; changing the terms later is a new version
that both sign again, and the version before stays in force until then.

Database triggers (migration 0002) keep the record honest: a version's terms and PDF
can't change once set, and signatures can't be changed or deleted. Change agreements
only through apps.agreements.services.
"""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.offers.models import Party


class Agreement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.PROTECT, related_name="agreement"
    )
    current_version = models.ForeignKey(
        "AgreementVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The version in force: the latest one both sides signed.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self) -> str:
        return f"Agreement for {self.booking_id}"

    @property
    def in_force(self) -> bool:
        return self.current_version_id is not None


class VersionStatus(models.TextChoices):
    AWAITING = "awaiting", "Waiting for signatures"
    ACTIVE = "active", "In force"
    SUPERSEDED = "superseded", "Replaced by a later version"
    DECLINED = "declined", "Change declined"
    VOIDED = "voided", "Replaced before it was signed"


class AgreementVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agreement = models.ForeignKey(Agreement, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveSmallIntegerField()
    terms = models.JSONField(encoder=DjangoJSONEncoder, help_text="apps.offers.terms, frozen.")
    terms_sha256 = models.CharField(max_length=64)
    offer = models.ForeignKey(
        "offers.Offer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The accepted offer version 1 was drawn up from.",
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Who asked for this change (empty for version 1).",
    )
    change_reason = models.TextField(max_length=1000, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)
    template = models.CharField(
        max_length=40, help_text="The template the PDF was drawn up with (apps.agreements.pdf)."
    )
    template_sha256 = models.CharField(max_length=64)
    pdf_key = models.CharField(max_length=300, blank=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    pdf_size = models.PositiveIntegerField(null=True, blank=True)
    rendered_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=VersionStatus.choices, default=VersionStatus.AWAITING
    )
    status_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    in_force_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["agreement", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["agreement", "number"], name="agreement_version_number_unique"
            ),
            models.UniqueConstraint(
                fields=["agreement"],
                condition=Q(status="awaiting"),
                name="agreement_one_awaiting_version",
            ),
            models.UniqueConstraint(
                fields=["agreement"],
                condition=Q(status="active"),
                name="agreement_one_active_version",
            ),
            models.CheckConstraint(
                condition=Q(status__in=VersionStatus.values), name="agreement_version_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"v{self.number} of {self.agreement_id} ({self.status})"

    @property
    def rendered(self) -> bool:
        return bool(self.pdf_sha256)


class Signature(models.Model):
    """One side's consent to one version: who, when, from where, and how it was proven."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(
        AgreementVersion, on_delete=models.PROTECT, related_name="signatures"
    )
    party = models.CharField(max_length=10, choices=Party.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    provider = models.CharField(max_length=30, help_text="The ESignProvider that took it.")
    provider_reference = models.CharField(max_length=120)
    document_sha256 = models.CharField(
        max_length=64, help_text="The PDF the signer saw: equal to the version's pdf_sha256."
    )
    consent_text = models.TextField(help_text="The statement the signer agreed to, word for word.")
    phone = models.CharField(max_length=20, blank=True, help_text="Re-confirmed by OTP.")
    otp_verified_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    device = models.CharField(max_length=120, blank=True)
    evidence = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    signed_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["signed_at"]
        constraints = [
            models.UniqueConstraint(fields=["version", "party"], name="signature_one_per_side"),
            models.CheckConstraint(
                condition=Q(party__in=Party.values), name="signature_party_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.party} signed {self.version_id}"
