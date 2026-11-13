import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import TalentFactory, UserFactory, VendorFactory
from apps.profiles.models import TalentProfile, VendorProfile
from apps.profiles.tests.factories import SkillFactory, TalentProfileFactory, VendorProfileFactory

pytestmark = pytest.mark.django_db

VENDOR_ME = reverse("profiles:vendor-me")
TALENT_ME = reverse("profiles:talent-me")
SKILLS = reverse("profiles:skills")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def years_ago(years: int, days: int = 0) -> str:
    today = timezone.localdate()
    try:
        born = today.replace(year=today.year - years)
    except ValueError:  # 29 February
        born = today.replace(year=today.year - years, day=28)
    return (born + datetime.timedelta(days=days)).isoformat()


# --- vendor -------------------------------------------------------------------------


def test_vendor_profile_is_created_then_completed():
    vendor = VendorFactory()
    client = client_for(vendor)
    assert client.get(VENDOR_ME).json()["code"] == "profile_not_found"

    first = client.patch(VENDOR_ME, {"business_name": "Zostel Manali"}, format="json")
    assert first.status_code == 201
    assert first.json()["profile_complete"] is False
    assert first.json()["missing_fields"] == [
        "business_type",
        "contact_name",
        "city",
        "state",
        "about",
    ]

    rest = {
        "business_type": "hostel",
        "contact_name": "Meera Shah",
        "city": "Manali",
        "state": "Himachal Pradesh",
        "about": "Riverside hostel.",
        "gstin": "02abcde1234f1z5",
    }
    second = client.patch(VENDOR_ME, rest, format="json")
    assert second.status_code == 200
    assert second.json()["profile_complete"] is True
    assert second.json()["missing_fields"] == []
    assert second.json()["gstin"] == "02ABCDE1234F1Z5"
    assert VendorProfile.objects.get(user=vendor).business_name == "Zostel Manali"
    # The account summary agrees.
    assert client.get(reverse("accounts:me")).json()["profile_complete"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("business_type", "spaceship"),
        ("state", "Atlantis"),
        ("gstin", "12345"),
        ("website", "not a url"),
        ("business_name", "x" * 151),
        ("about", "x" * 3001),
    ],
)
def test_vendor_field_validation(field, value):
    response = client_for(VendorFactory()).patch(VENDOR_ME, {field: value}, format="json")
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert field in response.json()["details"]
    assert not VendorProfile.objects.exists()


def test_clearing_a_required_field_makes_profile_incomplete():
    profile = VendorProfileFactory()
    client = client_for(profile.user)
    assert client.get(VENDOR_ME).json()["profile_complete"] is True
    response = client.patch(VENDOR_ME, {"about": ""}, format="json")
    assert response.json()["profile_complete"] is False
    assert response.json()["missing_fields"] == ["about"]


def test_role_gates_the_profile_endpoints():
    assert client_for(TalentFactory()).get(VENDOR_ME).status_code == 403
    assert client_for(VendorFactory()).patch(TALENT_ME, {}, format="json").status_code == 403
    assert client_for(UserFactory(role="")).get(TALENT_ME).status_code == 403
    assert APIClient().get(VENDOR_ME).status_code == 401


def test_soft_deleted_profile_is_not_silently_recreated():
    profile = VendorProfileFactory()
    profile.delete()
    client = client_for(profile.user)
    assert client.get(VENDOR_ME).status_code == 404
    response = client.patch(VENDOR_ME, {"business_name": "New"}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "profile_removed"


def test_read_only_fields_are_ignored():
    profile = VendorProfileFactory()
    other = VendorFactory()
    client_for(profile.user).patch(
        VENDOR_ME,
        {"id": "00000000-0000-0000-0000-000000000000", "user": str(other.pk)},
        format="json",
    )
    profile.refresh_from_db()
    assert profile.user_id != other.pk


# --- talent -------------------------------------------------------------------------


def complete_talent_body(skills):
    return {
        "display_name": "Asha",
        "bio": "Muralist and barista.",
        "talent_type": "artist",
        "skills": [s.slug for s in skills],
        "languages": ["en", "hi", "mr"],
        "home_city": "Pune",
        "emergency_contact_name": "Ravi Rao",
        "emergency_contact_phone": "98111 11111",
        "date_of_birth": years_ago(25),
        "instagram_handle": "@asha.paints",
    }


def test_talent_profile_round_trip():
    talent = TalentFactory()
    skills = [
        SkillFactory(slug="mural-art", name="Mural art"),
        SkillFactory(slug="barista", name="Barista"),
    ]
    client = client_for(talent)
    response = client.patch(TALENT_ME, complete_talent_body(skills), format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["profile_complete"] is True
    assert sorted(body["skills"]) == ["barista", "mural-art"]
    assert body["emergency_contact_phone"] == "+919811111111"
    assert body["instagram_handle"] == "asha.paints"
    profile = TalentProfile.objects.get(user=talent)
    assert set(profile.skills.values_list("slug", flat=True)) == {"mural-art", "barista"}

    # Replacing skills, partial update leaves the rest alone.
    response = client.patch(TALENT_ME, {"skills": ["barista"]}, format="json")
    assert response.json()["skills"] == ["barista"]
    assert response.json()["languages"] == ["en", "hi", "mr"]
    # Removing every skill makes it incomplete again.
    response = client.patch(TALENT_ME, {"skills": []}, format="json")
    assert response.json()["missing_fields"] == ["skills"]


def test_talent_must_be_18():
    client = client_for(TalentFactory())
    underage = client.patch(TALENT_ME, {"date_of_birth": years_ago(18, days=1)}, format="json")
    assert underage.status_code == 400
    assert "at least 18" in underage.json()["details"]["date_of_birth"][0]
    birthday = client.patch(TALENT_ME, {"date_of_birth": years_ago(18)}, format="json")
    assert birthday.status_code == 201


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("date_of_birth", "2999-01-01"),
        ("date_of_birth", "1900-01-01"),
        ("date_of_birth", "not-a-date"),
        ("languages", ["en", "klingon"]),
        ("languages", ["en", "en"]),
        ("languages", "en"),
        ("skills", ["no-such-skill"]),
        ("talent_type", "wizard"),
        ("emergency_contact_phone", "12345"),
        ("instagram_handle", "bad handle!"),
        ("display_name", "x" * 121),
    ],
)
def test_talent_field_validation(field, value):
    response = client_for(TalentFactory()).patch(TALENT_ME, {field: value}, format="json")
    assert response.status_code == 400
    assert field in response.json()["details"], response.json()


def test_inactive_skills_cannot_be_picked():
    SkillFactory(slug="retired", is_active=False)
    response = client_for(TalentFactory()).patch(TALENT_ME, {"skills": ["retired"]}, format="json")
    assert response.status_code == 400


def test_too_many_skills_and_languages():
    skills = [SkillFactory().slug for _ in range(16)]
    client = client_for(TalentFactory())
    assert client.patch(TALENT_ME, {"skills": skills}, format="json").status_code == 400
    languages = ["as", "bn", "en", "gu", "hi", "kn", "kok", "ml", "mr", "ne", "or"]
    assert client.patch(TALENT_ME, {"languages": languages}, format="json").status_code == 400


def test_emergency_contact_cannot_be_yourself():
    talent = TalentFactory()
    response = client_for(talent).patch(
        TALENT_ME, {"emergency_contact_phone": talent.phone}, format="json"
    )
    assert response.status_code == 400
    assert "emergency_contact_phone" in response.json()["details"]


def test_get_my_talent_profile():
    profile = TalentProfileFactory()
    body = client_for(profile.user).get(TALENT_ME).json()
    assert body["id"] == str(profile.pk)
    assert body["profile_complete"] is True


def test_skill_list_shows_active_skills_only():
    SkillFactory(slug="zz-active", name="ZZ Active")
    SkillFactory(slug="zz-retired", name="ZZ Retired", is_active=False)
    response = client_for(TalentFactory()).get(SKILLS)
    slugs = [s["slug"] for s in response.json()]
    assert "zz-active" in slugs
    assert "zz-retired" not in slugs


def test_seed_skills_migration_is_reversible():
    import importlib

    from django.apps import apps as global_apps

    from apps.profiles.models import Skill

    seed = importlib.import_module("apps.profiles.migrations.0003_seed_skills")
    seed.seed(global_apps, None)
    assert Skill.objects.filter(slug="photography").exists()
    in_use = Skill.objects.get(slug="yoga")
    TalentProfileFactory(skills=[in_use])
    seed.unseed(global_apps, None)
    assert not Skill.objects.filter(slug="photography").exists()
    assert Skill.objects.filter(slug="yoga").exists()  # still used by a profile
