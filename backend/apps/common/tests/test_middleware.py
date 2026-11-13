import logging
import re

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.common.middleware import RequestIDMiddleware, resolve_request_id
from apps.common.request_context import get_request_id

rf = RequestFactory()


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"HTTP_X_REQUEST_ID": "client-id-123"}, "client-id-123"),
        (
            {"HTTP_X_CLOUD_TRACE_CONTEXT": "105445AA7843BC8BF206B12000100000/1;o=1"},
            "105445aa7843bc8bf206b12000100000",
        ),
        (
            {
                "HTTP_X_REQUEST_ID": "client-id-123",
                "HTTP_X_CLOUD_TRACE_CONTEXT": "105445aa7843bc8bf206b12000100000/1",
            },
            "client-id-123",
        ),
    ],
)
def test_resolve_request_id_prefers_header_then_trace(meta, expected):
    assert resolve_request_id(meta) == expected


@pytest.mark.parametrize("bad", ["short", "has spaces in it", "x" * 129, "<script>alert</script>"])
def test_unsafe_incoming_ids_are_replaced(bad):
    generated = resolve_request_id({"HTTP_X_REQUEST_ID": bad})
    assert generated != bad
    assert re.fullmatch(r"[0-9a-f]{32}", generated)


def test_middleware_sets_request_attr_context_and_header():
    seen = {}

    def view(request):
        seen["attr"] = request.request_id
        seen["ctx"] = get_request_id()
        logging.getLogger("apps.test").info("inside")
        return HttpResponse("ok")

    response = RequestIDMiddleware(view)(rf.get("/", HTTP_X_REQUEST_ID="abc-12345678"))

    assert seen == {"attr": "abc-12345678", "ctx": "abc-12345678"}
    assert response["X-Request-ID"] == "abc-12345678"
    assert get_request_id() == ""  # reset after the request


def test_context_is_reset_even_when_view_raises():
    def view(request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        RequestIDMiddleware(view)(rf.get("/"))
    assert get_request_id() == ""


@pytest.mark.django_db
def test_every_response_carries_a_request_id(client):
    response = client.get("/api/v1/health/")
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])
