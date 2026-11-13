import uuid

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import Role, User
from apps.accounts.tests.factories import TalentFactory, VendorFactory

pytestmark = pytest.mark.django_db


def test_auth_user_model_is_custom():
    assert get_user_model() is User
    assert User.USERNAME_FIELD == "phone"


def test_create_user_normalises_and_defaults():
    user = User.objects.create_user("98765 43210", role=Role.VENDOR, email="  Host@Example.COM ")
    assert isinstance(user.pk, uuid.UUID)
    assert user.phone == "+919876543210"
    assert user.email == "host@example.com"
    assert user.role == Role.VENDOR
    assert user.is_active and not user.is_staff and not user.is_superuser
    assert not user.has_usable_password()  # OTP sign-in by default
    assert user.created_at and user.updated_at
    assert str(user) == "+919876543210"
    assert user.is_vendor and not user.is_talent and not user.is_admin_role


def test_create_user_with_password_and_blank_email():
    user = User.objects.create_user("+919876500001", "s3cret-pass!", role=Role.TALENT, email="")
    assert user.check_password("s3cret-pass!")
    assert user.email is None


def test_create_user_requires_valid_phone_and_role():
    with pytest.raises(ValidationError) as info:
        User.objects.create_user("123", role=Role.TALENT)
    assert "phone" in info.value.message_dict
    with pytest.raises(ValidationError) as info:
        User.objects.create_user("+919876500002", role="guest")
    assert "role" in info.value.message_dict


def test_create_superuser():
    user = User.objects.create_superuser("+919876500003", "admin-pass-123")
    assert user.role == Role.ADMIN and user.is_admin_role
    assert user.is_staff and user.is_superuser


@pytest.mark.parametrize(
    "extra", [{"role": Role.VENDOR}, {"is_staff": False}, {"is_superuser": False}]
)
def test_superuser_invariants(extra):
    with pytest.raises(ValueError):
        User.objects.create_superuser("+919876500004", "pw-123456789", **extra)


def test_phone_is_unique_after_normalisation():
    TalentFactory(phone="+919876500005")
    with pytest.raises(ValidationError) as info:
        User.objects.create_user("098765 00005", role=Role.VENDOR)
    assert "phone" in info.value.message_dict


def test_email_unique_case_insensitive_but_optional():
    VendorFactory(email="a@example.com")
    VendorFactory(email=None)
    VendorFactory(email=None)  # many users without email are fine
    with pytest.raises(IntegrityError), transaction.atomic():
        VendorFactory(email="A@EXAMPLE.com")


def test_role_check_constraint_in_database():
    user = TalentFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=user.pk).update(role="guest")


def test_clean_normalises_phone_and_reports_field_errors():
    user = User(phone="98765 00006", role=Role.TALENT, email="")
    user.clean()
    assert user.phone == "+919876500006"
    assert user.email is None
    user.phone = "bad"
    with pytest.raises(ValidationError) as info:
        user.clean()
    assert "phone" in info.value.message_dict


def test_natural_key_lookup_and_authentication_accept_local_format():
    user = TalentFactory(phone="+919876500007")
    assert User.objects.get_by_natural_key("98765 00007") == user
    with pytest.raises(User.DoesNotExist):
        User.objects.get_by_natural_key("not-a-phone")
    assert authenticate(username="98765 00007", password="test-password-123") == user
    assert authenticate(username="98765 00007", password="wrong") is None
    assert authenticate(username="garbage", password="test-password-123") is None


def test_inactive_users_cannot_authenticate():
    TalentFactory(phone="+919876500008", is_active=False)
    assert authenticate(username="+919876500008", password="test-password-123") is None


def test_role_is_empty_until_chosen():
    user = User.objects.create_user("+919876500077")
    assert user.role == "" and not user.has_role
    user.full_clean(exclude=["password"])


def test_database_rejects_unknown_roles():
    from django.db import IntegrityError, transaction

    user = User.objects.create_user("+919876500078")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=user.pk).update(role="guest")


def test_role_migration_refuses_to_reverse_with_roleless_users():
    import importlib

    from django.apps import apps as global_apps

    migration = importlib.import_module("apps.accounts.migrations.0002_role_chosen_after_sign_up")
    migration.refuse_if_role_missing(global_apps, None)  # no users: fine
    User.objects.create_user("+919876500079")
    with pytest.raises(RuntimeError, match="1 user"):
        migration.refuse_if_role_missing(global_apps, None)
