"""The Razorpay Route client's requests, against a fake HTTP layer."""

from datetime import date

import pytest
import requests

from apps.money.gateway.base import DayTotals, GatewayError
from apps.money.gateway.razorpay import RazorpayEscrowGateway, signature


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
    calls, replies = [], []

    def request(method, url, json=None, params=None, auth=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "params": dict(params or {})})
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(requests, "request", request)
    return calls, replies


def test_orders_and_refunds(http):
    calls, replies = http
    gateway = RazorpayEscrowGateway()
    replies += [
        Response(200, {"id": "order_1", "amount": 511800}),
        Response(200, {"id": "rfnd_1"}),
    ]
    order = gateway.create_order(amount_paise=511800, receipt="escrow-x", notes={"b": 1})
    assert (order.id, order.amount_paise) == ("order_1", 511800)
    assert calls[0]["json"] == {
        "amount": 511800,
        "currency": "INR",
        "receipt": "escrow-x",
        "payment_capture": 1,
        "notes": {"b": "1"},
    }
    assert gateway.refund(payment_id="pay_1", amount_paise=50, notes={}) == "rfnd_1"
    assert calls[1]["url"].endswith("/payments/pay_1/refund")


def test_errors_become_gateway_errors(http, settings):
    _, replies = http
    gateway = RazorpayEscrowGateway()
    replies += [
        Response(400, {"error": {"description": "Bad amount"}}),
        Response(500, ValueError()),
        requests.ConnectionError(),
    ]
    with pytest.raises(GatewayError, match="Bad amount"):
        gateway.refund(payment_id="p", amount_paise=1, notes={})
    with pytest.raises(GatewayError, match="HTTP 500"):
        gateway.refund(payment_id="p", amount_paise=1, notes={})
    with pytest.raises(GatewayError, match="couldn't reach"):
        gateway.refund(payment_id="p", amount_paise=1, notes={})
    settings.RAZORPAY_KEY_ID = ""
    with pytest.raises(GatewayError, match="aren't configured"):
        gateway.refund(payment_id="p", amount_paise=1, notes={})


def test_day_totals_page_through_and_skip_failures(http):
    calls, replies = http
    payments = [{"amount": 100, "fee": 2, "status": "captured"}] * 100
    replies += [
        Response(200, {"items": payments}),
        Response(
            200,
            {
                "items": [
                    {"amount": 7, "fee": 1, "status": "refunded"},
                    {"amount": 999, "status": "failed"},
                ]
            },
        ),
        Response(
            200,
            {"items": [{"amount": 30, "status": "processed"}, {"amount": 5, "status": "pending"}]},
        ),
    ]
    totals = RazorpayEscrowGateway().day_totals(date(2026, 11, 18))
    assert totals == DayTotals(captured=10_007, refunded=30, fees=201)
    assert calls[1]["params"]["skip"] == 100
    assert calls[0]["params"]["to"] - calls[0]["params"]["from"] == 86_399


def test_webhooks_are_verified(settings):
    settings.RAZORPAY_ESCROW_WEBHOOK_SECRET = "s3cret"  # noqa: S105
    body = b'{"event": "refund.processed", "payload": {"refund": {"entity": {"id": "r"}}}}'
    headers = {"X-Razorpay-Signature": signature(body, "s3cret"), "X-Razorpay-Event-Id": "e1"}
    data = RazorpayEscrowGateway().parse_webhook(body, headers)
    assert (data.event_id, data.event, data.refund) == ("e1", "refund.processed", {"id": "r"})
    with pytest.raises(GatewayError, match="signature"):
        RazorpayEscrowGateway().parse_webhook(body + b" ", headers)
    bad = b"not json"
    with pytest.raises(GatewayError, match="isn't JSON"):
        RazorpayEscrowGateway().parse_webhook(
            bad, {**headers, "X-Razorpay-Signature": signature(bad, "s3cret")}
        )
