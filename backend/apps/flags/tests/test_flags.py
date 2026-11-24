import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, UserFactory
from apps.common.models import AuditLog
from apps.flags import services
from apps.flags.models import FeatureFlag
from apps.flags.registry import FLAGS
from apps.money.tests.helpers import ensure_accounts, paid_booking

pytestmark = pytest.mark.django_db


def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.delete(services.CACHE_KEY)


def test_defaults_apply_without_rows():
    assert services.all_flags() == {key: flag.default for key, flag in FLAGS.items()}


def test_set_flag_is_audited_and_takes_effect_at_once(django_capture_on_commit_callbacks):
    admin = AdminUserFactory(roles=["finance"])
    assert services.is_enabled("escrow_funding")
    with django_capture_on_commit_callbacks(execute=True):
        services.set_flag("escrow_funding", False, actor=admin, reason="Gateway incident")
    assert not services.is_enabled("escrow_funding")
    entry = AuditLog.objects.get(action="flags.changed")
    assert entry.before == {"enabled": True}
    assert entry.after == {"enabled": False, "reason": "Gateway incident"}


def test_reason_is_required_and_unknown_flags_refused():
    admin = AdminUserFactory(roles=["ops"])
    with pytest.raises(ValueError):
        services.set_flag("escrow_funding", False, actor=admin, reason="  ")
    with pytest.raises(services.UnknownFlag):
        services.set_flag("nope", False, actor=admin, reason="x")
    with pytest.raises(services.UnknownFlag):
        services.is_enabled("nope")


def test_clients_read_values():
    body = client(UserFactory()).get("/api/v1/flags/").json()
    assert body == {"escrow_funding": True, "sos_live_sharing": True, "ai_safety_checks": True}
    assert APIClient().get("/api/v1/flags/").status_code == 401


@pytest.mark.parametrize(
    ("roles", "allowed"),
    [([], False), (["support"], False), (["ops"], True), (["trust"], True), (["finance"], True)],
)
def test_only_permitted_staff_change_flags(roles, allowed):
    api = client(AdminUserFactory(roles=roles))
    response = api.post(
        "/api/v1/admin/flags/sos_live_sharing/", {"enabled": False, "reason": "Map outage"}
    )
    assert response.status_code == (200 if allowed else 403)
    assert FeatureFlag.objects.filter(key="sos_live_sharing").exists() is allowed
    if allowed:
        listing = api.get("/api/v1/admin/flags/").json()
        assert {f["key"]: f["enabled"] for f in listing}["sos_live_sharing"] is False
        assert (
            api.post("/api/v1/admin/flags/nope/", {"enabled": False, "reason": "x"}).status_code
            == 404
        )


def test_escrow_funding_switched_off_refuses_new_funding(django_capture_on_commit_callbacks):
    ensure_accounts()
    booking = paid_booking()
    with django_capture_on_commit_callbacks(execute=True):
        services.set_flag(
            "escrow_funding", False, actor=AdminUserFactory(roles=["finance"]), reason="Test"
        )
    response = client(booking.vendor).post(f"/api/v1/bookings/{booking.pk}/escrow/fund/")
    assert response.status_code == 503
    assert response.json()["code"] == "escrow_funding_off"
