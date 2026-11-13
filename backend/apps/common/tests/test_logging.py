import json
import logging
import sys

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
