import pytest

from apps.accounts.tests.factories import AdminUserFactory
from apps.common.models import AuditLog
from apps.profiles.tests.factories import TalentProfileFactory, VendorProfileFactory
from apps.verification.constants import BadgeKind, CaseStatus, CheckType
from apps.verification.services import checks
from apps.verification.services.cases import Decision, active_badge_kinds, decide
from apps.verification.tests.factories import PIN, MediaFileFactory, client_for

pytestmark = pytest.mark.django_db


def approved_property(profile):
    user = profile.user
    photos = [
        checks.GeoPhoto(media_id=str(MediaFileFactory(owner=user).pk), **PIN) for _ in range(3)
    ]
    case = checks.submit_property(user, **PIN, pin_confirmed=True, photos=photos)
    return decide(case.pk, Decision.APPROVE, reviewer=AdminUserFactory())


def test_changing_the_address_reopens_the_property_check_and_removes_the_badge():
    profile = VendorProfileFactory(address="Old Manali Road")
    case = approved_property(profile)
    assert BadgeKind.PROPERTY_VERIFIED in active_badge_kinds(profile.user)

    profile.address = "Vashisht, Manali"
    profile.save()

    case.refresh_from_db()
    assert case.status == CaseStatus.IN_REVIEW
    assert case.details["address"] == "Vashisht, Manali"
    assert "property address" in case.reason
    assert BadgeKind.PROPERTY_VERIFIED not in active_badge_kinds(profile.user)
    assert AuditLog.objects.filter(action="verification.case.in_review").exists()

    decide(case.pk, Decision.APPROVE, reviewer=AdminUserFactory())
    assert BadgeKind.PROPERTY_VERIFIED in active_badge_kinds(profile.user)


def test_business_name_reopens_both_vendor_checks_it_appears_in():
    profile = VendorProfileFactory(address="Old Manali Road")
    approved_property(profile)
    business = checks.submit_business(profile.user, pan="ABCPE1234F")
    decide(business.pk, Decision.APPROVE, reviewer=AdminUserFactory())

    profile.business_name = "River Hostel"
    profile.save()

    statuses = dict(profile.user.verification_cases.values_list("check_type", "status"))
    assert statuses == {
        CheckType.PROPERTY: CaseStatus.IN_REVIEW,
        CheckType.BUSINESS: CaseStatus.IN_REVIEW,
    }


def test_unwatched_or_unchanged_fields_do_nothing():
    profile = VendorProfileFactory(address="Old Manali Road")
    case = approved_property(profile)
    profile.about = "Now with a cafe."
    profile.address = "Old Manali Road"  # same value
    profile.save()
    case.refresh_from_db()
    assert case.status == CaseStatus.APPROVED


def test_pending_cases_get_the_new_values_without_changing_status():
    profile = VendorProfileFactory(address="Old Manali Road")
    case = checks.submit_business(profile.user, pan="ABCPE1234F")
    profile.gstin = "27ABCPE1234F1Z5"
    profile.save()
    case.refresh_from_db()
    assert case.status == CaseStatus.SUBMITTED
    assert case.details["gstin_last_four"] == "F1Z5"


def test_changing_the_instagram_handle_through_the_api_reopens_social():
    profile = TalentProfileFactory(instagram_handle="old.handle")
    case = checks.submit_social(profile.user)
    decide(case.pk, Decision.APPROVE, reviewer=AdminUserFactory())

    response = client_for(profile.user).patch(
        "/api/v1/profiles/talent/me/", {"instagram_handle": "@new.handle"}, format="json"
    )
    assert response.status_code == 200

    case.refresh_from_db()
    assert case.status == CaseStatus.IN_REVIEW
    assert case.subject_id == "instagram:new.handle"
    assert BadgeKind.SOCIAL_VERIFIED not in active_badge_kinds(profile.user)
