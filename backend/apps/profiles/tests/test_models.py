import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.tests.factories import TalentFactory, VendorFactory
from apps.profiles.models import TalentProfile, VendorProfile
from apps.profiles.tests.factories import TalentProfileFactory, VendorProfileFactory

pytestmark = pytest.mark.django_db


def test_profiles_link_to_their_user():
    talent = TalentProfileFactory(full_name="Asha Rao")
    vendor = VendorProfileFactory(business_name="Zostel Manali")
    assert talent.user.talent_profile == talent
    assert vendor.user.vendor_profile == vendor
    assert str(talent) == "Asha Rao"
    assert str(vendor) == "Zostel Manali"
    talent.full_clean()
    vendor.full_clean()


@pytest.mark.parametrize(
    ("profile_cls", "wrong_user_factory", "kwargs"),
    [
        (TalentProfile, VendorFactory, {"full_name": "X"}),
        (
            VendorProfile,
            TalentFactory,
            {"business_name": "X", "property_type": "hostel", "city": "Goa", "state": "Goa"},
        ),
    ],
)
def test_profile_requires_matching_role(profile_cls, wrong_user_factory, kwargs):
    profile = profile_cls(user=wrong_user_factory(), **kwargs)
    with pytest.raises(ValidationError) as info:
        profile.full_clean()
    assert "user" in info.value.message_dict


def test_one_profile_per_user():
    profile = TalentProfileFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        TalentProfile.objects.create(user=profile.user, full_name="Second")


@pytest.mark.parametrize(
    ("gstin", "valid"),
    [("29ABCDE1234F1Z5", True), ("29ABCDE1234F1Y5", False), ("12345", False), ("", True)],
)
def test_gstin_format(gstin, valid):
    profile = VendorProfileFactory.build(user=VendorFactory(), gstin=gstin)
    if valid:
        profile.full_clean()
    else:
        with pytest.raises(ValidationError) as info:
            profile.full_clean()
        assert "gstin" in info.value.message_dict


def test_soft_deleted_profile_is_hidden():
    profile = VendorProfileFactory()
    profile.delete()
    assert not VendorProfile.objects.exists()
    assert VendorProfile.all_objects.get() == profile


def test_admin_lists_include_soft_deleted(client):
    admin = User.objects.create_superuser("+919876599998", "admin-pass-123")
    client.force_login(admin)
    deleted = TalentProfileFactory(full_name="Deleted Person")
    deleted.delete()
    VendorProfileFactory()
    talent_list = client.get(reverse("admin:profiles_talentprofile_changelist"))
    assert talent_list.status_code == 200
    assert b"Deleted Person" in talent_list.content
    assert client.get(reverse("admin:profiles_vendorprofile_changelist")).status_code == 200
