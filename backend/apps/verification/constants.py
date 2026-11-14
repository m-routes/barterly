"""Verification vocabulary: what is checked, the case lifecycle, and the badges it earns."""

from dataclasses import dataclass

from django.db import models

from apps.accounts.models import Role


class SubjectType(models.TextChoices):
    USER = "user", "User"
    PROPERTY = "property", "Property"
    SOCIAL_ACCOUNT = "social_account", "Social account"


class CheckType(models.TextChoices):
    ID_SELFIE = "id_selfie", "Government ID and selfie"
    BUSINESS = "business_registration", "PAN and GST"
    PROPERTY = "property", "Property photos and map pin"
    SOCIAL = "social_account", "Linked social account"
    CERTIFICATE = "certificate", "Certificates"
    REFERENCE = "reference", "Reference"


class CaseStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    SUBMITTED = "submitted", "Submitted"
    IN_REVIEW = "in_review", "In review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CHANGES_REQUESTED = "changes_requested", "Changes requested"
    EXPIRED = "expired", "Expired"


S = CaseStatus
# Every allowed status change. Anything else is a bug or a stale request.
TRANSITIONS: dict[str, frozenset[str]] = {
    S.NOT_STARTED: frozenset({S.SUBMITTED}),
    S.SUBMITTED: frozenset({S.SUBMITTED, S.IN_REVIEW, S.APPROVED, S.REJECTED, S.CHANGES_REQUESTED}),
    S.IN_REVIEW: frozenset({S.IN_REVIEW, S.APPROVED, S.REJECTED, S.CHANGES_REQUESTED}),
    # Approved cases go back to review when a verified detail changes or is resubmitted;
    # trust can also withdraw an approval (e.g. fraud found later).
    S.APPROVED: frozenset({S.IN_REVIEW, S.REJECTED, S.EXPIRED}),
    S.REJECTED: frozenset({S.SUBMITTED}),
    S.CHANGES_REQUESTED: frozenset({S.SUBMITTED}),
    S.EXPIRED: frozenset({S.SUBMITTED}),
}
# Statuses the user can resubmit from.
RESUBMITTABLE = frozenset({S.NOT_STARTED, S.SUBMITTED, S.REJECTED, S.CHANGES_REQUESTED, S.EXPIRED})
# Statuses a reviewer can decide on.
DECIDABLE = frozenset({S.SUBMITTED, S.IN_REVIEW})


class BadgeKind(models.TextChoices):
    ID_VERIFIED = "id_verified", "ID verified"
    PROPERTY_VERIFIED = "property_verified", "Property verified"
    LICENCE_VERIFIED = "licence_verified", "Licence verified"
    SOCIAL_VERIFIED = "social_verified", "Social verified"
    REFERENCE_CHECKED = "reference_checked", "Reference checked"
    TRUSTED_MEMBER = "trusted_member", "Trusted member"


class DocumentType(models.TextChoices):
    AADHAAR = "aadhaar", "Aadhaar"
    PASSPORT = "passport", "Passport"
    DRIVING_LICENCE = "driving_licence", "Driving licence"
    VOTER_ID = "voter_id", "Voter ID"
    SELFIE = "selfie", "Selfie"
    PAN = "pan", "PAN"
    GSTIN = "gstin", "GSTIN"
    PROPERTY_PHOTO = "property_photo", "Property photo"
    CERTIFICATE = "certificate", "Certificate"


# IDs the KYC provider checks. Their images stay with the provider, never with us.
ID_DOCUMENT_TYPES = frozenset(
    {
        DocumentType.AADHAAR,
        DocumentType.PASSPORT,
        DocumentType.DRIVING_LICENCE,
        DocumentType.VOTER_ID,
    }
)
ID_DOCUMENT_CHOICES = [(t.value, t.label) for t in DocumentType if t in ID_DOCUMENT_TYPES]
# The only documents that may point at one of our uploads (neither is an identity document).
MEDIA_DOCUMENT_TYPES = frozenset({DocumentType.PROPERTY_PHOTO, DocumentType.CERTIFICATE})


class DocumentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    VERIFIED = "verified", "Verified"
    FAILED = "failed", "Failed"


@dataclass(frozen=True)
class CheckRule:
    subject: str
    badge: str
    required: bool
    valid_days: int
    # Profile fields whose change sends an approved case back to review.
    watched_fields: tuple[str, ...] = ()


CHECKS: dict[str, dict[str, CheckRule]] = {
    Role.VENDOR: {
        CheckType.ID_SELFIE: CheckRule(SubjectType.USER, BadgeKind.ID_VERIFIED, True, 730),
        CheckType.BUSINESS: CheckRule(
            SubjectType.USER,
            BadgeKind.LICENCE_VERIFIED,
            True,
            365,
            watched_fields=("business_name", "gstin"),
        ),
        CheckType.PROPERTY: CheckRule(
            SubjectType.PROPERTY,
            BadgeKind.PROPERTY_VERIFIED,
            True,
            365,
            # Watched on the Property itself: see PROPERTY_WATCHED_FIELDS.
        ),
    },
    Role.TALENT: {
        CheckType.ID_SELFIE: CheckRule(SubjectType.USER, BadgeKind.ID_VERIFIED, True, 730),
        CheckType.SOCIAL: CheckRule(
            SubjectType.SOCIAL_ACCOUNT,
            BadgeKind.SOCIAL_VERIFIED,
            True,
            180,
            watched_fields=("instagram_handle",),
        ),
        CheckType.CERTIFICATE: CheckRule(SubjectType.USER, BadgeKind.LICENCE_VERIFIED, False, 730),
        CheckType.REFERENCE: CheckRule(SubjectType.USER, BadgeKind.REFERENCE_CHECKED, True, 365),
    },
}

# Property fields whose change sends that property's approved case back to review.
PROPERTY_WATCHED_FIELDS = ("name", "address", "city", "state", "latitude", "longitude")

# Badges a user needs, by role, to also be a trusted member.
TRUSTED_MEMBER_REQUIRES: dict[str, frozenset[str]] = {
    role: frozenset(rule.badge for rule in checks.values() if rule.required)
    for role, checks in CHECKS.items()
}


def rule_for(role: str, check_type: str) -> CheckRule | None:
    return CHECKS.get(role, {}).get(check_type)
