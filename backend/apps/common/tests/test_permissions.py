from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.common.permissions import IsAdminRole, IsOwner, IsTalent, IsVendor

pytestmark = pytest.mark.django_db


def req(user):
    return SimpleNamespace(user=user)


@pytest.mark.parametrize(
    ("permission", "allowed_factory"),
    [(IsVendor, VendorFactory), (IsTalent, TalentFactory), (IsAdminRole, AdminUserFactory)],
)
def test_role_permissions_allow_only_their_role(permission, allowed_factory):
    allowed = allowed_factory()
    others = [
        f() for f in (VendorFactory, TalentFactory, AdminUserFactory) if f is not allowed_factory
    ]

    assert permission().has_permission(req(allowed), None)
    for user in others:
        assert not permission().has_permission(req(user), None)
    assert not permission().has_permission(req(AnonymousUser()), None)
    assert not permission().has_permission(req(None), None)


@pytest.mark.parametrize("permission", [IsVendor, IsTalent, IsAdminRole])
def test_role_permissions_reject_inactive_users(permission):
    factory = {IsVendor: VendorFactory, IsTalent: TalentFactory, IsAdminRole: AdminUserFactory}
    user = factory[permission](is_active=False)
    assert not permission().has_permission(req(user), None)


def test_role_permissions_have_clear_messages():
    assert "vendors" in IsVendor.message
    assert "talent" in IsTalent.message
    assert "admins" in IsAdminRole.message


class TestIsOwner:
    def test_requires_authentication(self):
        assert IsOwner().has_permission(req(TalentFactory()), None)
        assert not IsOwner().has_permission(req(AnonymousUser()), None)

    def test_default_owner_field_is_user(self):
        owner, other = TalentFactory(), TalentFactory()
        obj = SimpleNamespace(user=owner)
        view = SimpleNamespace()
        assert IsOwner().has_object_permission(req(owner), view, obj)
        assert not IsOwner().has_object_permission(req(other), view, obj)

    def test_nested_owner_field(self):
        vendor = VendorFactory()
        obj = SimpleNamespace(listing=SimpleNamespace(vendor=vendor))
        view = SimpleNamespace(owner_field="listing__vendor")
        assert IsOwner().has_object_permission(req(vendor), view, obj)

    def test_owner_field_can_be_a_raw_id(self):
        user = TalentFactory()
        view = SimpleNamespace(owner_field="user_id")
        assert IsOwner().has_object_permission(req(user), view, SimpleNamespace(user_id=user.pk))

    def test_object_is_the_user(self):
        user = TalentFactory()
        view = SimpleNamespace(owner_field="")
        assert IsOwner().has_object_permission(req(user), view, user)
        assert not IsOwner().has_object_permission(req(TalentFactory()), view, user)

    def test_missing_owner_denies(self):
        user = TalentFactory()
        view = SimpleNamespace(owner_field="listing__vendor")
        assert not IsOwner().has_object_permission(req(user), view, SimpleNamespace(listing=None))
        assert not IsOwner().has_object_permission(
            req(user), SimpleNamespace(), SimpleNamespace(user=None)
        )
