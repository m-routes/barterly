import pytest

from apps.accounts.tests.factories import AdminUserFactory, UserFactory
from apps.profiles.services import get_profile, is_profile_complete
from apps.profiles.tests.factories import TalentProfileFactory, VendorProfileFactory

pytestmark = pytest.mark.django_db


def test_no_role_is_incomplete():
    user = UserFactory(role="")
    assert get_profile(user) is None
    assert is_profile_complete(user) is False


def test_role_without_profile_is_incomplete():
    assert is_profile_complete(UserFactory(role="vendor")) is False


def test_complete_profiles():
    assert is_profile_complete(VendorProfileFactory().user) is True
    assert is_profile_complete(TalentProfileFactory().user) is True


def test_partial_profiles_are_incomplete():
    vendor = VendorProfileFactory(bare=True)
    assert vendor.missing_fields() == ["business_type", "contact_name", "city", "state", "about"]
    assert is_profile_complete(vendor.user) is False
    talent = TalentProfileFactory(bare=True)
    assert "skills" in talent.missing_fields()
    assert is_profile_complete(talent.user) is False


def test_soft_deleted_profile_does_not_count():
    profile = TalentProfileFactory()
    profile.delete()
    assert is_profile_complete(profile.user) is False


def test_admins_are_always_complete():
    assert is_profile_complete(AdminUserFactory()) is True
