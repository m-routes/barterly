import pytest

from apps.accounts.tests.factories import AdminUserFactory, UserFactory
from apps.profiles.services import is_profile_complete
from apps.profiles.tests.factories import TalentProfileFactory, VendorProfileFactory

pytestmark = pytest.mark.django_db


def test_no_role_is_incomplete():
    assert is_profile_complete(UserFactory(role="")) is False


def test_role_without_profile_is_incomplete():
    assert is_profile_complete(UserFactory(role="vendor")) is False


def test_matching_profile_is_complete():
    assert is_profile_complete(VendorProfileFactory().user) is True
    assert is_profile_complete(TalentProfileFactory().user) is True


def test_soft_deleted_profile_does_not_count():
    profile = TalentProfileFactory()
    profile.delete()
    assert is_profile_complete(profile.user) is False


def test_admins_are_always_complete():
    assert is_profile_complete(AdminUserFactory()) is True
