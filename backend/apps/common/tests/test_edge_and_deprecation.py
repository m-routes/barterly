from datetime import date

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.common import deprecation
from apps.common.deprecation import MINIMUM_NOTICE_DAYS, Deprecated, headers_for
from apps.common.middleware import DeprecationMiddleware, EdgeForwardedForMiddleware

rf = RequestFactory()
LB = "34.120.0.1"


def forwarded_after(xff: str | None) -> str | None:
    seen = {}

    def view(request):
        seen["xff"] = request.META.get("HTTP_X_FORWARDED_FOR")
        return HttpResponse()

    meta = {} if xff is None else {"HTTP_X_FORWARDED_FOR": xff}
    with override_settings(EDGE_PROXY_IPS=[LB]):
        EdgeForwardedForMiddleware(view)(rf.get("/api/v1/me/", **meta))
    return seen["xff"]


@pytest.mark.parametrize(
    ("incoming", "outgoing"),
    [
        # Through the load balancer: its hop goes, the client is last again.
        (f"203.0.113.9, {LB}", "203.0.113.9"),
        (f"6.6.6.6, 203.0.113.9, {LB}", "6.6.6.6, 203.0.113.9"),
        # Straight to run.app: Cloud Run appended the real caller; a forged LB entry
        # earlier in the header changes nothing.
        (f"{LB}, 198.51.100.7", f"{LB}, 198.51.100.7"),
        ("198.51.100.7", "198.51.100.7"),
        # Only the LB itself (no client before it): left alone.
        (LB, LB),
        (None, None),
    ],
)
def test_edge_hop_is_dropped_only_when_last(incoming, outgoing):
    assert forwarded_after(incoming) == outgoing


def test_without_edge_ips_nothing_changes():
    def view(request):
        return HttpResponse(request.META["HTTP_X_FORWARDED_FOR"])

    with override_settings(EDGE_PROXY_IPS=[]):
        response = EdgeForwardedForMiddleware(view)(
            rf.get("/", HTTP_X_FORWARDED_FOR=f"203.0.113.9, {LB}")
        )
    assert response.content.decode() == f"203.0.113.9, {LB}"


@pytest.fixture
def deprecated(monkeypatch):
    entry = Deprecated(
        path=r"^/api/v1/old/$",
        deprecated_on=date(2027, 1, 1),
        sunset_on=date(2027, 4, 1),
        methods=frozenset({"GET"}),
    )
    monkeypatch.setattr(deprecation, "DEPRECATIONS", [entry])
    return entry


def test_deprecated_operations_get_rfc_headers(deprecated, caplog):
    request = rf.get("/api/v1/old/", HTTP_X_CLIENT_PLATFORM="ios", HTTP_X_CLIENT_VERSION="1.0.3")
    with caplog.at_level("INFO", logger="apps.api"):
        response = DeprecationMiddleware(lambda r: HttpResponse())(request)
    record = next(r for r in caplog.records if getattr(r, "deprecated_call", False))
    assert (record.client_platform, record.client_version) == ("ios", "1.0.3")
    assert response["Deprecation"] == "@1798761600"
    assert response["Sunset"] == "Thu, 01 Apr 2027 00:00:00 GMT"
    assert response["Link"] == f'<{deprecation.POLICY_URL}>; rel="deprecation"'


def test_other_methods_and_paths_are_untouched(deprecated):
    assert headers_for("POST", "/api/v1/old/") == {}
    assert headers_for("GET", "/api/v1/new/") == {}


def test_every_deprecation_gives_the_minimum_notice():
    for entry in deprecation.DEPRECATIONS:
        assert (entry.sunset_on - entry.deprecated_on).days >= MINIMUM_NOTICE_DAYS, entry.path
