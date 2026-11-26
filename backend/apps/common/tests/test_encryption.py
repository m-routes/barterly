import base64
import os

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings

from apps.common import encryption
from apps.common.encryption import PREFIX, DecryptionError, decrypt, encrypt
from apps.profiles.models import TalentProfile
from apps.profiles.tests.factories import TalentProfileFactory


def key(kid: str) -> str:
    return f"{kid}:{base64.b64encode(os.urandom(32)).decode()}"


@pytest.fixture(autouse=True)
def _fresh_keys():
    encryption.reset_keys()
    yield
    encryption.reset_keys()


def raw(profile, column):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column} FROM profiles_talentprofile WHERE id = %s", [profile.pk])  # noqa: S608
        return cursor.fetchone()[0]


def test_round_trip_and_fresh_nonce():
    a, b = encrypt("Ravi", context="x.y"), encrypt("Ravi", context="x.y")
    assert a != b and a.startswith(PREFIX)
    assert decrypt(a, context="x.y") == "Ravi"


def test_ciphertext_is_bound_to_its_column():
    with pytest.raises(DecryptionError):
        decrypt(encrypt("Ravi", context="a.b"), context="a.c")


def test_tampering_is_detected():
    stored = encrypt("Ravi", context="x.y")
    blob = bytearray(base64.b64decode(stored.rsplit(":", 1)[1]))
    blob[-1] ^= 1
    with pytest.raises(DecryptionError):
        decrypt(
            stored.rsplit(":", 1)[0] + ":" + base64.b64encode(bytes(blob)).decode(), context="x.y"
        )


@pytest.mark.django_db
def test_emergency_contact_is_encrypted_at_rest():
    profile = TalentProfileFactory(
        emergency_contact_name="Ravi Kumar", emergency_contact_phone="+919812345678"
    )
    assert "Ravi" not in raw(profile, "emergency_contact_name")
    assert raw(profile, "emergency_contact_phone").startswith(PREFIX)
    fresh = TalentProfile.objects.get(pk=profile.pk)
    assert fresh.emergency_contact_name == "Ravi Kumar"
    assert fresh.emergency_contact_phone == "+919812345678"


@pytest.mark.django_db
def test_only_blank_comparisons_are_allowed():
    assert TalentProfile.objects.filter(emergency_contact_phone="").count() >= 0
    with pytest.raises(ValueError, match="Encrypted"):
        list(TalentProfile.objects.filter(emergency_contact_phone="+919812345678"))
    with pytest.raises(Exception):  # noqa: B017 - FieldError: no such lookup
        list(TalentProfile.objects.filter(emergency_contact_name__icontains="ravi"))


@pytest.mark.django_db
def test_plaintext_rows_stay_readable_then_get_encrypted_and_rotated(settings):
    old, new = key("k1"), key("k2")
    settings.FIELD_ENCRYPTION_KEYS = old
    encryption.reset_keys()
    profile = TalentProfileFactory(emergency_contact_name="Asha")
    with connection.cursor() as cursor:  # a row from before encryption
        cursor.execute(
            "UPDATE profiles_talentprofile SET emergency_contact_name = 'Old' WHERE id = %s",
            [profile.pk],
        )
    assert TalentProfile.objects.get(pk=profile.pk).emergency_contact_name == "Old"
    with pytest.raises(CommandError):
        call_command("reencrypt_fields", "--check")

    call_command("reencrypt_fields")
    assert encryption.key_id(raw(profile, "emergency_contact_name")) == "k1"
    call_command("reencrypt_fields", "--check")

    with override_settings(FIELD_ENCRYPTION_KEYS=f"{new},{old}"):  # rotation: new first
        encryption.reset_keys()
        assert TalentProfile.objects.get(pk=profile.pk).emergency_contact_name == "Old"
        call_command("reencrypt_fields")
        assert encryption.key_id(raw(profile, "emergency_contact_name")) == "k2"

    with override_settings(FIELD_ENCRYPTION_KEYS=new):  # old key dropped
        encryption.reset_keys()
        assert TalentProfile.objects.get(pk=profile.pk).emergency_contact_name == "Old"
