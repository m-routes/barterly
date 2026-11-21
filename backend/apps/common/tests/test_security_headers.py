"""Transport and browser-hardening headers (ASVS 14.4, 3.4, 4.2.2)."""

import pytest
from django.conf import settings
from django.test import override_settings

from apps.common.middleware import SecurityHeadersMiddleware, _origin

pytestmark = pytest.mark.django_db


def test_api_responses_get_the_strict_policy(client):
    response = client.get("/api/v1/health/")
    csp = response["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "camera=()" in response["Permissions-Policy"]
    assert response["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"


def test_error_responses_are_hardened_too(client):
    response = client.get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    assert "default-src 'none'" in response["Content-Security-Policy"]


def test_admin_policy_allows_no_inline_script(client):
    response = client.get("/admin/login/")
    csp = response["Content-Security-Policy"]
    script = next(d for d in csp.split("; ") if d.startswith("script-src"))
    assert "'unsafe-inline'" not in script
    assert "'unsafe-eval'" not in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp


@pytest.mark.parametrize("method", ["get", "options"])
def test_no_cors_for_any_origin(client, method):
    response = getattr(client, method)(
        "/api/v1/health/",
        HTTP_ORIGIN="https://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert "Access-Control-Allow-Origin" not in response
    assert "Access-Control-Allow-Credentials" not in response


def test_admin_post_without_csrf_token_is_refused():
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    response = client.post("/admin/login/", {"username": "x", "password": "y"})
    assert response.status_code == 403


def test_request_body_limits():
    assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE <= 2.5 * 1024 * 1024
    assert settings.DATA_UPLOAD_MAX_NUMBER_FIELDS <= 1000


@override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1024)
def test_oversized_json_body_is_refused(client):
    response = client.post(
        "/api/v1/auth/refresh/",
        data="{" + '"x": "' + "a" * 4096 + '"}',
        content_type="application/json",
    )
    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"


@override_settings(STATIC_URL="https://storage.googleapis.com/bucket/static/")
def test_admin_policy_allows_the_static_bucket():
    middleware = SecurityHeadersMiddleware(lambda request: None)
    assert "script-src 'self' https://storage.googleapis.com" in middleware.admin_policy


@pytest.mark.parametrize(
    ("url", "origin"),
    [("static/", ""), ("https://cdn.example/a/b/", "https://cdn.example")],
)
def test_origin(url, origin):
    assert _origin(url) == origin
