import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.tests.factories import TalentFactory, VendorFactory
from apps.accounts.tests.fakes import UNAVAILABLE, token_for
from apps.accounts.throttles import ExchangeIPThrottle, ExchangePhoneThrottle
from apps.common.models import AuditLog
from apps.profiles.tests.factories import VendorProfileFactory

pytestmark = pytest.mark.django_db

EXCHANGE = reverse("accounts:auth-exchange")
REFRESH = reverse("accounts:auth-refresh")
LOGOUT = reverse("accounts:auth-logout")
ME = reverse("accounts:me")
ROLE = reverse("accounts:me-role")
PHONE = "+919812345678"


@pytest.fixture
def api():
    return APIClient()


def exchange(api, phone=PHONE, **extra):
    return api.post(EXCHANGE, {"id_token": token_for(phone)}, format="json", **extra)


def bearer(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# --- exchange -----------------------------------------------------------------------


def test_first_sign_in_creates_user_without_role(api):
    response = exchange(api)
    assert response.status_code == 200
    body = response.json()
    assert body["is_new_user"] is True
    assert body["needs_role"] is True
    assert body["profile_complete"] is False
    assert body["user"]["phone"] == PHONE
    assert body["user"]["role"] == ""

    user = User.objects.get(phone=PHONE)
    assert not user.has_usable_password()
    assert user.last_login is not None
    entry = AuditLog.objects.get(action="user.signed_up")
    assert entry.actor == user
    assert entry.object_id == str(user.pk)
    assert entry.after == {"phone": PHONE, "provider": "fake"}


def test_access_token_authenticates_api_calls(api):
    access = exchange(api).json()["access"]
    response = bearer(access).get(ME)
    assert response.status_code == 200
    assert response.json()["phone"] == PHONE


def test_returning_user_is_fetched_not_created(api):
    vendor = VendorFactory(phone=PHONE)
    VendorProfileFactory(user=vendor)
    body = exchange(api).json()
    assert body["is_new_user"] is False
    assert body["needs_role"] is False
    assert body["profile_complete"] is True
    assert body["user"]["id"] == str(vendor.pk)
    assert User.objects.count() == 1
    assert not AuditLog.objects.filter(action="user.signed_up").exists()


def test_phone_in_token_is_normalised(api):
    talent = TalentFactory(phone=PHONE)
    response = api.post(EXCHANGE, {"id_token": token_for("98123 45678")}, format="json")
    assert response.json()["user"]["id"] == str(talent.pk)


def test_invalid_token_is_401(api):
    response = api.post(EXCHANGE, {"id_token": "forged"}, format="json")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_sign_in_token"
    assert response["WWW-Authenticate"] == 'Bearer realm="api"'
    assert not User.objects.exists()


def test_token_without_valid_phone_is_401(api):
    response = api.post(EXCHANGE, {"id_token": token_for("not-a-phone")}, format="json")
    assert response.status_code == 401


def test_missing_token_is_validation_error(api):
    response = api.post(EXCHANGE, {}, format="json")
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert "id_token" in response.json()["details"]


def test_provider_outage_is_503(api):
    response = api.post(EXCHANGE, {"id_token": UNAVAILABLE}, format="json")
    assert response.status_code == 503
    assert response.json()["code"] == "auth_provider_unavailable"


def test_disabled_account_cannot_sign_in(api):
    TalentFactory(phone=PHONE, is_active=False)
    response = exchange(api)
    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"


def test_session_cookie_is_ignored_by_exchange(api):
    # The exchange takes only the provider token; an admin session doesn't change that.
    api.force_login(VendorFactory())
    assert api.post(EXCHANGE, {"id_token": "forged"}, format="json").status_code == 401


# --- rate limits --------------------------------------------------------------------


@pytest.fixture
def tight_limits(monkeypatch):
    monkeypatch.setattr(ExchangeIPThrottle, "THROTTLE_RATES", {"auth_exchange_ip": "3/min"})
    monkeypatch.setattr(ExchangePhoneThrottle, "THROTTLE_RATES", {"auth_exchange_phone": "2/min"})


def test_exchange_is_limited_per_ip(api, tight_limits):
    for n in range(3):
        assert exchange(api, phone=f"+91981234500{n}").status_code == 200
    blocked = exchange(api, phone="+919812345009")
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "throttled"
    assert blocked.json()["details"]["retry_after_seconds"] > 0
    # Another address still gets through.
    assert exchange(api, phone="+919812345009", REMOTE_ADDR="10.0.0.9").status_code == 200


def test_invalid_tokens_count_towards_the_ip_limit(api, tight_limits):
    for _ in range(3):
        api.post(EXCHANGE, {"id_token": "forged"}, format="json")
    assert exchange(api).status_code == 429


def test_exchange_is_limited_per_phone(api, tight_limits):
    for n in range(2):
        assert exchange(api, REMOTE_ADDR=f"10.0.1.{n}").status_code == 200
    blocked = exchange(api, REMOTE_ADDR="10.0.1.9")
    assert blocked.status_code == 429
    # Other phones are unaffected.
    assert exchange(api, phone="+919812300000", REMOTE_ADDR="10.0.1.9").status_code == 200


def test_ip_limit_uses_last_proxy_hop_not_client_supplied_hops(api, tight_limits, monkeypatch):
    monkeypatch.setattr(ExchangeIPThrottle, "get_ident", _ident_with_proxies(1))
    for n in range(3):
        # A client rotating a fake first hop is still one address to us.
        exchange(api, phone=f"+91981234500{n}", HTTP_X_FORWARDED_FOR=f"1.1.1.{n}, 203.0.113.7")
    blocked = exchange(api, phone="+919812345009", HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.7")
    assert blocked.status_code == 429


def _ident_with_proxies(count):
    from rest_framework.throttling import BaseThrottle

    def get_ident(self, request):
        self.num_proxies = count  # what TRUSTED_PROXY_COUNT sets in deployed settings
        return BaseThrottle.get_ident(self, request)

    return get_ident


# --- refresh and logout -------------------------------------------------------------


def test_refresh_rotates_and_blacklists_the_old_token(api):
    tokens = exchange(api).json()
    response = api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code == 200
    new = response.json()
    assert set(new) == {"access", "refresh"}
    assert new["refresh"] != tokens["refresh"]
    assert bearer(new["access"]).get(ME).status_code == 200

    reused = api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert reused.status_code == 401
    assert reused.json()["code"] == "token_not_valid"


def test_refresh_rejects_disabled_users(api):
    tokens = exchange(api).json()
    User.objects.filter(phone=PHONE).update(is_active=False)
    response = api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code == 401
    assert bearer(tokens["access"]).get(ME).status_code == 401


def test_refresh_rejects_garbage(api):
    response = api.post(REFRESH, {"refresh": "nope"}, format="json")
    assert response.status_code == 401
    assert response.json()["code"] == "token_not_valid"


def test_logout_blacklists_the_refresh_token(api):
    tokens = exchange(api).json()
    response = api.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code == 204
    assert api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json").status_code == 401
    again = api.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json")
    assert again.status_code == 401


def test_logout_rejects_access_tokens_and_garbage(api):
    tokens = exchange(api).json()
    assert api.post(LOGOUT, {"refresh": tokens["access"]}, format="json").status_code == 401
    assert api.post(LOGOUT, {"refresh": "nope"}, format="json").status_code == 401
    assert api.post(LOGOUT, {}, format="json").status_code == 400


# --- /me/ and role selection --------------------------------------------------------


def test_me_requires_a_token(api):
    response = api.get(ME)
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert response["WWW-Authenticate"] == 'Bearer realm="api"'


def test_choose_role_once(api):
    access = exchange(api).json()["access"]
    client = bearer(access)

    response = client.post(ROLE, {"role": "vendor"}, format="json")
    assert response.status_code == 200
    assert response.json()["role"] == "vendor"
    assert response.json()["profile_complete"] is False
    user = User.objects.get(phone=PHONE)
    assert user.role == Role.VENDOR
    entry = AuditLog.objects.get(action="user.role_selected")
    assert (entry.before, entry.after, entry.actor) == ({"role": ""}, {"role": "vendor"}, user)

    again = client.post(ROLE, {"role": "talent"}, format="json")
    assert again.status_code == 409
    assert again.json()["code"] == "role_already_set"
    user.refresh_from_db()
    assert user.role == Role.VENDOR

    assert exchange(api).json()["needs_role"] is False


@pytest.mark.parametrize("role", ["admin", "superuser", ""])
def test_admin_and_unknown_roles_cannot_be_chosen(api, role):
    client = bearer(exchange(api).json()["access"])
    response = client.post(ROLE, {"role": role}, format="json")
    assert response.status_code == 400
    assert "role" in response.json()["details"]
    assert User.objects.get(phone=PHONE).role == ""


def test_choose_role_requires_sign_in(api):
    assert api.post(ROLE, {"role": "talent"}, format="json").status_code == 401
