"""The Razorpay client's requests, against a fake HTTP layer."""

from datetime import UTC, datetime

import pytest
import requests

from apps.billing.gateway.base import GatewayError
from apps.billing.gateway.razorpay import RazorpayGateway, signature


class Response:
    def __init__(self, status: int, body: object):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.fixture
def http(monkeypatch, settings):
    settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET = "rzp_test_key", "secret"
    calls = []
    replies = []

    def request(method, url, json=None, auth=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "auth": auth})
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(requests, "request", request)
    return calls, replies


def test_creates_a_subscription_with_a_trial(http):
    calls, replies = http
    replies.append(
        Response(200, {"id": "sub_1", "status": "created", "short_url": "https://rzp.io/x"})
    )
    start = datetime(2027, 2, 1, tzinfo=UTC)
    made = RazorpayGateway().create_subscription(
        plan_id="plan_growth", start_at=start, notes={"vendor_id": 7}
    )
    assert (made.id, made.checkout_url) == ("sub_1", "https://rzp.io/x")
    sent = calls[0]
    assert (sent["method"], sent["url"]) == ("POST", "https://api.razorpay.com/v1/subscriptions")
    assert sent["auth"] == ("rzp_test_key", "secret")
    assert sent["json"]["start_at"] == int(start.timestamp())
    assert sent["json"]["notes"] == {"vendor_id": "7"}


def test_changes_plan_and_cancels(http):
    calls, replies = http
    replies.extend([Response(200, {}), Response(200, {})])
    gateway = RazorpayGateway()
    gateway.change_plan("sub_1", plan_id="plan_pro", at_cycle_end=False)
    gateway.cancel("sub_1", at_cycle_end=True)
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["json"] == {"plan_id": "plan_pro", "schedule_change_at": "now"}
    assert calls[1]["url"].endswith("/subscriptions/sub_1/cancel")
    assert calls[1]["json"] == {"cancel_at_cycle_end": 1}


def test_errors_say_what_razorpay_said(http):
    _, replies = http
    replies.append(Response(400, {"error": {"description": "The plan id is invalid"}}))
    with pytest.raises(GatewayError, match="The plan id is invalid"):
        RazorpayGateway().cancel("sub_1", at_cycle_end=False)
    replies.append(Response(500, ValueError("not json")))
    with pytest.raises(GatewayError, match="HTTP 500"):
        RazorpayGateway().cancel("sub_1", at_cycle_end=False)
    replies.append(requests.ConnectionError("down"))
    with pytest.raises(GatewayError, match="couldn't reach"):
        RazorpayGateway().cancel("sub_1", at_cycle_end=False)


def test_needs_keys(settings):
    settings.RAZORPAY_KEY_ID = ""
    with pytest.raises(GatewayError, match="aren't configured"):
        RazorpayGateway().cancel("sub_1", at_cycle_end=False)


def test_webhooks_need_the_right_signature_and_json(settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "whsec"  # noqa: S105 (a test value)
    body = b'{"event": "subscription.activated", "payload": {}}'
    good = {"X-Razorpay-Signature": signature(body, "whsec"), "X-Razorpay-Event-Id": "evt_1"}
    event = RazorpayGateway().parse_webhook(body, good)
    assert (event.event, event.event_id) == ("subscription.activated", "evt_1")
    with pytest.raises(GatewayError, match="signature"):
        RazorpayGateway().parse_webhook(body, {**good, "X-Razorpay-Signature": "x"})
    bad = b"not json"
    with pytest.raises(GatewayError, match="isn't JSON"):
        RazorpayGateway().parse_webhook(bad, {"X-Razorpay-Signature": signature(bad, "whsec")})
