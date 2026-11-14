import pytest

from apps.accounts.tests.factories import AdminUserFactory
from apps.common.models import AuditLog
from apps.profiles.tests.factories import TalentProfileFactory, VendorProfileFactory
from apps.properties.tests.factories import PropertyFactory, add_photos
from apps.verification.constants import BadgeKind, CaseStatus
from apps.verification.services import checks
from apps.verification.services.cases import Decision, active_badge_kinds, decide
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def approved_property(**kwargs):
    prop = PropertyFactory(**kwargs)
    add_photos(prop)
    case = checks.submit_property(prop.vendor, prop)
    return prop, decide(case.pk, Decision.APPROVE, reviewer=AdminUserFactory())


def test_changing_the_address_reopens_the_property_check_and_removes_the_badge():
    prop, case = approved_property()
    assert BadgeKind.PROPERTY_VERIFIED in active_badge_kinds(prop.vendor)

    prop.address = "Vashisht, Manali"
    prop.save()

    case.refresh_from_db()
    prop.refresh_from_db()
    assert case.status == CaseStatus.IN_REVIEW
    assert prop.verification_status == CaseStatus.IN_REVIEW
    assert case.details["address"] == "Vashisht, Manali"
    assert "address" in case.reason
    assert BadgeKind.PROPERTY_VERIFIED not in active_badge_kinds(prop.vendor)
    assert AuditLog.objects.filter(action="verification.case.in_review").exists()

    decide(case.pk, Decision.APPROVE, reviewer=AdminUserFactory())
    assert BadgeKind.PROPERTY_VERIFIED in active_badge_kinds(prop.vendor)


def test_moving_the_pin_through_the_api_reopens_it():
    prop, case = approved_property()
    response = client_for(prop.vendor).patch(
        f"/api/v1/properties/{prop.pk}/",
        {"latitude": "32.250000", "longitude": "77.190000", "location_confirmed": True},
        format="json",
    )
    assert response.status_code == 200, response.json()
    case.refresh_from_db()
    assert case.status == CaseStatus.IN_REVIEW
    assert "map pin" in case.reason
    assert case.details["pin"] == {"latitude": 32.25, "longitude": 77.19}


def test_unwatched_or_unchanged_fields_do_nothing():
    prop, case = approved_property()
    prop.amenities = ["wifi"]
    prop.women_friendly = True
    prop.address = prop.address  # same value
    prop.save()
    case.refresh_from_db()
    assert case.status == CaseStatus.APPROVED


def test_business_name_reopens_the_business_check():
    profile = VendorProfileFactory()
    business = checks.submit_business(profile.user, pan="ABCPE1234F")
    decide(business.pk, Decision.APPROVE, reviewer=AdminUserFactory())

    profile.business_name = "River Hostel"
    profile.save()

    business.refresh_from_db()
    assert business.status == CaseStatus.IN_REVIEW
    assert business.details["business_name"] == "River Hostel"


def test_pending_cases_get_the_new_values_without_changing_status():
    profile = VendorProfileFactory()
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
