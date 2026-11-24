import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, UserFactory
from apps.appversions import services
from apps.appversions.models import AppVersionPolicy
from apps.common.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.delete(services.CACHE_KEY)
    yield
    cache.delete(services.CACHE_KEY)


def staff(*roles):
    api = APIClient()
    api.force_authenticate(AdminUserFactory(roles=list(roles)))
    return api


def set_android(minimum="1.2.0", latest="1.4.0", **extra):
    with_defaults = {"store_url": "", "message": "", "reason": "API v1 contract change", **extra}
    services.set_policy(
        "android",
        minimum_version=minimum,
        latest_version=latest,
        actor=AdminUserFactory(roles=["ops"]),
        **with_defaults,
    )
    cache.delete(services.CACHE_KEY)


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [
        ("1.4.2", (1, 4, 2)),
        (" 1.4.2+17 ", (1, 4, 2)),
        ("2.0.0-rc1", (2, 0, 0)),
        ("1.4", None),
        ("", None),
        ("v1.2.3", None),
    ],
)
def test_parse(raw, parsed):
    assert services.parse(raw) == parsed


def test_defaults_force_nothing():
    body = APIClient().get("/api/v1/app/version/?platform=android&version=0.0.1").json()
    assert body["minimum_version"] == "0.0.0"
    assert body["update"] == "none"
    assert body["store_url"].startswith("https://play.google.com/")


@pytest.mark.parametrize(
    ("version", "update"),
    [("1.1.9", "required"), ("1.2.0", "available"), ("1.3.5+40", "available"), ("1.4.0", "none")],
)
def test_status_for_a_version(version, update):
    set_android()
    body = (
        APIClient().get("/api/v1/app/version/", {"platform": "android", "version": version}).json()
    )
    assert body["update"] == update
    assert (body["minimum_version"], body["latest_version"]) == ("1.2.0", "1.4.0")


def test_unknown_platform_is_a_validation_error():
    response = APIClient().get("/api/v1/app/version/?platform=symbian")
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_set_policy_is_audited_and_validated(django_capture_on_commit_callbacks):
    admin = AdminUserFactory(roles=["ops"])
    with django_capture_on_commit_callbacks(execute=True):
        services.set_policy(
            "ios", minimum_version="1.0.0", latest_version="1.1.0", actor=admin, reason="Launch"
        )
    assert services.policy_for("ios").latest_version == "1.1.0"
    entry = AuditLog.objects.get(action="appversions.changed")
    assert entry.before["minimum_version"] == "0.0.0"
    assert entry.after["minimum_version"] == "1.0.0"
    assert entry.after["reason"] == "Launch"
    with pytest.raises(services.InvalidVersion):
        services.set_policy(
            "ios", minimum_version="2.0.0", latest_version="1.0.0", actor=admin, reason="x"
        )
    with pytest.raises(services.InvalidVersion):
        services.set_policy(
            "ios", minimum_version="two", latest_version="2.0.0", actor=admin, reason="x"
        )
    with pytest.raises(ValueError):
        services.set_policy(
            "ios", minimum_version="1.0.0", latest_version="1.0.0", actor=admin, reason=" "
        )


@pytest.mark.parametrize(
    ("roles", "allowed"),
    [([], False), (["support"], False), (["finance"], False), (["ops"], True)],
)
def test_only_ops_set_versions(roles, allowed):
    api = staff(*roles)
    response = api.put(
        "/api/v1/admin/app-versions/android/",
        {"minimum_version": "1.2.0", "latest_version": "1.3.0", "reason": "Breaking change"},
        format="json",
    )
    assert response.status_code == (200 if allowed else 403)
    assert AppVersionPolicy.objects.filter(platform="android").exists() is allowed
    if allowed:
        assert response.json()["minimum_version"] == "1.2.0"
        listing = staff("ops").get("/api/v1/admin/app-versions/").json()
        assert [p["platform"] for p in listing] == ["android", "ios"]


def test_admin_set_rejects_bad_input():
    api = staff("ops")
    bad = api.put(
        "/api/v1/admin/app-versions/android/",
        {"minimum_version": "1.3.0", "latest_version": "1.2.0", "reason": "x"},
        format="json",
    )
    assert bad.status_code == 400
    missing = api.put("/api/v1/admin/app-versions/windows/", {}, format="json")
    assert missing.status_code == 404


class TestMiddleware:
    HEADERS = {"HTTP_X_CLIENT_PLATFORM": "android"}

    def call(self, version, path="/api/v1/me/", **headers):
        api = APIClient()
        api.force_authenticate(UserFactory())
        return api.get(path, **{**self.HEADERS, "HTTP_X_CLIENT_VERSION": version, **headers})

    def test_old_apps_get_426_upgrade_required(self):
        set_android(message="Update for the new payouts.")
        response = self.call("1.1.0")
        assert response.status_code == 426
        body = response.json()
        assert body["code"] == "upgrade_required"
        assert body["message"] == "Update for the new payouts."
        assert body["details"]["minimum_version"] == "1.2.0"
        assert response["X-Request-ID"]

    def test_supported_unknown_and_headerless_clients_pass(self):
        set_android()
        assert self.call("1.2.0").status_code == 200
        assert self.call("garbage").status_code == 200
        assert self.call("1.0.0", HTTP_X_CLIENT_PLATFORM="symbian").status_code == 200
        api = APIClient()
        api.force_authenticate(UserFactory())
        assert api.get("/api/v1/me/").status_code == 200  # the web sends no headers

    def test_version_check_and_health_stay_reachable(self):
        set_android()
        assert self.call("1.0.0", path="/api/v1/app/version/?platform=android").status_code == 200
        assert self.call("1.0.0", path="/api/v1/health/").status_code in (200, 503)
