import json
import logging
import sys
from types import SimpleNamespace

import pytest

from apps.common.logging import JsonFormatter, RequestIDFilter, logging_config
from apps.common.request_context import reset_request_id, set_request_id


def make_record(msg="hello %s", args=("world",), level=logging.INFO, **extra):
    record = logging.getLogger("apps.test").makeRecord(
        "apps.test", level, __file__, 1, msg, args, None, extra=extra or None
    )
    RequestIDFilter().filter(record)
    return record


def test_filter_attaches_current_request_id():
    token = set_request_id("req-abcdef12")
    try:
        record = make_record()
    finally:
        reset_request_id(token)
    assert record.request_id == "req-abcdef12"
    assert make_record().request_id == "-"


def test_json_formatter_emits_one_object_with_standard_and_extra_fields():
    token = set_request_id("req-abcdef12")
    try:
        record = make_record(booking_id=7, amount="1500.00")
    finally:
        reset_request_id(token)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["severity"] == "INFO"
    assert payload["logger"] == "apps.test"
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-abcdef12"
    assert payload["booking_id"] == 7
    assert payload["amount"] == "1500.00"
    assert payload["timestamp"].endswith("+00:00")
    assert "exception" not in payload


def test_json_formatter_includes_exception_and_stringifies_unknown_types():
    try:
        raise ValueError("bad")
    except ValueError:
        record = logging.getLogger("x").makeRecord(
            "x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info(), extra={"obj": object()}
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: bad" in payload["exception"]
    assert payload["obj"].startswith("<object object")


def test_json_formatter_includes_stack_info():
    record = make_record()
    record.stack_info = "Stack (most recent call last):\n  frame"
    assert "frame" in json.loads(JsonFormatter().format(record))["stack"]


def test_logging_config_selects_formatter_and_level():
    config = logging_config(fmt="plain", level="DEBUG")
    assert config["handlers"]["console"]["formatter"] == "plain"
    assert config["handlers"]["console"]["filters"] == ["request_id"]
    assert config["root"]["level"] == "DEBUG"
    assert logging_config()["handlers"]["console"]["formatter"] == "json"


def test_logging_config_rejects_unknown_format():
    with pytest.raises(ValueError):
        logging_config(fmt="xml")


def test_settings_use_structured_logging(settings):
    assert settings.LOGGING["handlers"]["console"]["filters"] == ["request_id"]


def test_filter_prefers_the_request_attached_to_the_record():
    request = SimpleNamespace(request_id="req-from-request", method="GET", path="/api/v1/me/")
    record = make_record(request=request)
    assert record.request_id == "req-from-request"


def test_json_formatter_replaces_request_object_with_method_and_path():
    request = SimpleNamespace(request_id="req-from-request", method="GET", path="/api/v1/me/")
    payload = json.loads(JsonFormatter().format(make_record(request=request)))
    assert "request" not in payload
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/me/"
    assert payload["request_id"] == "req-from-request"


@pytest.mark.django_db
def test_django_4xx_warnings_carry_the_response_request_id(client, caplog):
    with caplog.at_level(logging.WARNING, logger="django.request"):
        response = client.get("/api/v1/me/", HTTP_X_REQUEST_ID="trace-me-12345")
    assert response.status_code == 403

    [record] = [r for r in caplog.records if r.name == "django.request"]
    RequestIDFilter().filter(record)  # what the console handler does in production
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == response["X-Request-ID"] == "trace-me-12345"
    assert payload["path"] == "/api/v1/me/"
    assert payload["status_code"] == 403
