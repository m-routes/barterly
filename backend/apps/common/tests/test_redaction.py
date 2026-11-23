import json
import logging

import pytest

from apps.common.logging import JsonFormatter, RedactPIIFilter
from apps.common.redaction import MASK, redact, redact_text
from config.sentry import scrub_breadcrumb, scrub_event


@pytest.mark.parametrize(
    "secret",
    [
        "+91 98765 43210",
        "9876543210",
        "+919876543210",
        "asha@example.com",
        "asha.k@okaxis",
        "ABCDE1234F",
        "1234 5678 9012",
        "50100123456789",
        "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl",
        "Bearer abcdefghijklmnop",
    ],
)
def test_patterns_are_masked(secret):
    out = redact_text(f"value={secret} end")
    assert secret not in out
    assert MASK in out


@pytest.mark.parametrize(
    "safe",
    [
        "booking 3f2a9c1e-0b7d-4a1e-9c3e-1f2d3e4c5b6a confirmed",
        "took 1234 ms",
        "amount 150000 paise",
        "2026-11-21T10:00:00+05:30",
        "1.234567890",
    ],
)
def test_ordinary_values_survive(safe):
    assert redact_text(safe) == safe


def test_sensitive_keys_are_masked_whatever_the_value():
    data = {
        "emergency_contact": {"name": "Ravi", "relation": "brother"},
        "payout": {"provider_ref": "fa_123", "amount": 500},
        "latitude": 15.5,
        "status": "ok",
        "phone": "",
    }
    assert redact(data) == {
        "emergency_contact": MASK,
        "payout": {"provider_ref": MASK, "amount": 500},
        "latitude": MASK,
        "status": "ok",
        "phone": "",
    }


def test_log_records_are_redacted_before_formatting():
    record = logging.makeLogRecord(
        {"msg": "OTP sent to %s", "args": ("+919876543210",), "levelname": "INFO"}
    )
    record.phone = "+919876543210"
    record.booking_id = "b-1"
    record.request_id = "-"
    RedactPIIFilter().filter(record)
    line = json.loads(JsonFormatter().format(record))
    assert "9876543210" not in json.dumps(line)
    assert line["phone"] == MASK
    assert line["booking_id"] == "b-1"


def test_sentry_event_is_scrubbed():
    event = {
        "event_id": "abc",
        "message": "payout to 50100123456789 failed",
        "user": {"id": "u1", "email": "asha@example.com", "ip_address": "1.2.3.4"},
        "request": {
            "url": "https://api/x?phone=9876543210",
            "query_string": "phone=9876543210",
            "cookies": {"sessionid": "s"},
            "data": {"otp": "123456"},
            "headers": {"Authorization": "Bearer abcdefghijkl", "Accept": "json"},
        },
        "extra": {"emergency_contact_phone": "9876543210"},
        "exception": {"values": [{"type": "Boom", "value": "asha@example.com not found"}]},
    }
    out = scrub_event(event)
    dumped = json.dumps(out)
    for leaked in ["50100123456789", "asha@example.com", "9876543210", "123456", "1.2.3.4"]:
        assert leaked not in dumped
    assert out["user"] == {"id": "u1"}
    assert "cookies" not in out["request"]
    assert out["request"]["headers"]["Accept"] == "json"
    assert out["exception"]["values"][0]["type"] == "Boom"


def test_breadcrumbs_are_scrubbed():
    crumb = {"category": "query", "message": "SELECT ... WHERE phone = '9876543210'"}
    assert "9876543210" not in scrub_breadcrumb(crumb)["message"]
