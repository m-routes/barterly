from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.common.models import AuditLog
from apps.properties.tests.factories import PropertyFactory
from apps.verification.constants import BadgeKind, CaseStatus, CheckType, DocumentType
from apps.verification.models import Badge, VerificationDocument
from apps.verification.services.cases import (
    CheckNotAvailable,
    Decision,
    InvalidTransition,
    active_badge_kinds,
    decide,
    expire_due_cases,
    locked_case,
    transition,
)
from apps.verification.tests.factories import CaseFactory, MediaFileFactory

pytestmark = pytest.mark.django_db


def approve(user, check_type, reviewer=None, prop=None):
    if check_type == CheckType.PROPERTY:
        prop = prop or PropertyFactory(vendor=user)
        case = CaseFactory(user=user, check_type=check_type, property=prop, subject_type="property")
    else:
        case = CaseFactory(user=user, check_type=check_type, status=CaseStatus.SUBMITTED)
    return decide(case.pk, Decision.APPROVE, reviewer=reviewer or AdminUserFactory())


def test_locked_case_is_created_once_per_check_and_role_checked():
    vendor = VendorFactory()
    with transaction.atomic():
        first = locked_case(vendor, CheckType.BUSINESS)
        again = locked_case(vendor, CheckType.BUSINESS)
    assert first.pk == again.pk
    assert first.status == CaseStatus.NOT_STARTED
    prop_a, prop_b = PropertyFactory(vendor=vendor), PropertyFactory(vendor=vendor)
    with transaction.atomic():
        case_a = locked_case(vendor, CheckType.PROPERTY, prop=prop_a)
        case_b = locked_case(vendor, CheckType.PROPERTY, prop=prop_b)
    assert case_a.pk != case_b.pk
    assert case_a.subject_type == "property" and case_a.subject_id == str(prop_a.pk)
    with pytest.raises(ValueError), transaction.atomic():
        locked_case(vendor, CheckType.PROPERTY)
    with pytest.raises(CheckNotAvailable), transaction.atomic():
        locked_case(vendor, CheckType.REFERENCE)


def test_illegal_transitions_are_refused():
    case = CaseFactory(status=CaseStatus.NOT_STARTED)
    with pytest.raises(InvalidTransition):
        transition(case, CaseStatus.APPROVED, actor=None)


def test_approval_grants_badge_sets_expiry_and_audits():
    reviewer = AdminUserFactory()
    vendor = VendorFactory()
    case = approve(vendor, CheckType.ID_SELFIE, reviewer)

    assert case.status == CaseStatus.APPROVED
    assert case.reviewer == reviewer
    assert case.expires_at > timezone.now() + timedelta(days=700)
    badge = Badge.objects.get(user=vendor, kind=BadgeKind.ID_VERIFIED)
    assert badge.is_active and badge.case == case and badge.granted_by == reviewer
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"verification.case.approved", "verification.badge.granted"} <= actions
    entry = AuditLog.objects.get(action="verification.case.approved")
    assert entry.before["status"] == "submitted" and entry.after["status"] == "approved"


def test_reject_needs_a_reason_and_revoke_removes_badge():
    reviewer = AdminUserFactory()
    vendor = VendorFactory()
    case = approve(vendor, CheckType.BUSINESS, reviewer)
    with pytest.raises(ValueError):
        decide(case.pk, Decision.REVOKE, reviewer=reviewer, reason=" ")

    case = decide(case.pk, Decision.REVOKE, reviewer=reviewer, reason="GSTIN cancelled.")
    assert case.status == CaseStatus.REJECTED
    badge = Badge.objects.get(user=vendor, kind=BadgeKind.LICENCE_VERIFIED)
    assert badge.revoked_at is not None
    assert badge.revoke_reason == "GSTIN cancelled."
    assert AuditLog.objects.filter(action="verification.badge.revoked").exists()


def test_decisions_only_on_waiting_cases():
    reviewer = AdminUserFactory()
    case = CaseFactory(status=CaseStatus.NOT_STARTED)
    with pytest.raises(InvalidTransition):
        decide(case.pk, Decision.APPROVE, reviewer=reviewer)
    case = CaseFactory(status=CaseStatus.SUBMITTED, check_type=CheckType.BUSINESS)
    case = decide(case.pk, Decision.START_REVIEW, reviewer=reviewer)
    assert case.status == CaseStatus.IN_REVIEW and case.reviewer == reviewer
    case = decide(case.pk, Decision.REQUEST_CHANGES, reviewer=reviewer, reason="Blurry photos.")
    assert case.status == CaseStatus.CHANGES_REQUESTED and case.reason == "Blurry photos."
    with pytest.raises(InvalidTransition):
        decide(case.pk, Decision.REVOKE, reviewer=reviewer, reason="x")


def test_trusted_member_follows_the_required_badges():
    vendor = VendorFactory()
    approve(vendor, CheckType.ID_SELFIE)
    approve(vendor, CheckType.BUSINESS)
    assert BadgeKind.TRUSTED_MEMBER not in active_badge_kinds(vendor)
    property_case = approve(vendor, CheckType.PROPERTY)
    assert BadgeKind.TRUSTED_MEMBER in active_badge_kinds(vendor)

    decide(
        property_case.pk, Decision.REVOKE, reviewer=AdminUserFactory(), reason="Not their property."
    )
    kinds = active_badge_kinds(vendor)
    assert BadgeKind.PROPERTY_VERIFIED not in kinds
    assert BadgeKind.TRUSTED_MEMBER not in kinds
    trusted = Badge.objects.get(user=vendor, kind=BadgeKind.TRUSTED_MEMBER)
    assert "property_verified" in trusted.revoke_reason


def test_property_badge_stays_while_another_property_is_verified():
    vendor = VendorFactory()
    first = approve(vendor, CheckType.PROPERTY)
    second = approve(vendor, CheckType.PROPERTY)
    assert first.property.verification_status == CaseStatus.APPROVED

    decide(first.pk, Decision.REVOKE, reviewer=AdminUserFactory(), reason="Closed down.")
    first.property.refresh_from_db()
    assert first.property.verification_status == CaseStatus.REJECTED
    assert BadgeKind.PROPERTY_VERIFIED in active_badge_kinds(vendor)

    decide(second.pk, Decision.REVOKE, reviewer=AdminUserFactory(), reason="Closed down.")
    assert BadgeKind.PROPERTY_VERIFIED not in active_badge_kinds(vendor)


def test_property_cases_need_their_property():
    with pytest.raises(IntegrityError), transaction.atomic():
        CaseFactory(check_type=CheckType.PROPERTY, subject_type="property")


def test_optional_certificates_are_not_needed_for_trusted_talent():
    talent = TalentFactory()
    for check in (CheckType.ID_SELFIE, CheckType.SOCIAL, CheckType.REFERENCE):
        approve(talent, check)
    assert BadgeKind.TRUSTED_MEMBER in active_badge_kinds(talent)
    assert BadgeKind.LICENCE_VERIFIED not in active_badge_kinds(talent)


def test_expiry_moves_cases_and_removes_badges():
    vendor = VendorFactory()
    case = approve(vendor, CheckType.ID_SELFIE)
    assert expire_due_cases() == 0
    assert expire_due_cases(now=case.expires_at + timedelta(seconds=1)) == 1
    case.refresh_from_db()
    assert case.status == CaseStatus.EXPIRED
    assert BadgeKind.ID_VERIFIED not in active_badge_kinds(vendor)


def test_one_active_badge_per_kind():
    vendor = VendorFactory()
    Badge.objects.create(
        user=vendor, kind=BadgeKind.ID_VERIFIED, granted_at=timezone.now(), grant_reason="x"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Badge.objects.create(
            user=vendor, kind=BadgeKind.ID_VERIFIED, granted_at=timezone.now(), grant_reason="y"
        )


def test_id_documents_can_never_point_at_an_upload():
    case = CaseFactory()
    media = MediaFileFactory(owner=case.user)
    with pytest.raises(IntegrityError), transaction.atomic():
        VerificationDocument.objects.create(
            case=case, document_type=DocumentType.AADHAAR, media=media
        )
    VerificationDocument.objects.create(
        case=case, document_type=DocumentType.PROPERTY_PHOTO, media=media
    )
