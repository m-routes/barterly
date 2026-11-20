"""The RazorpayX client's requests, against a fake HTTP layer."""

from datetime import date

import pytest
import requests

from apps.money.gateway.base import GatewayError
from apps.money.gateway.payouts import BankDetails, RazorpayXProvider, signature
from apps.money.tests.test_razorpay import Response


@pytest.fixture
def http(monkeypatch, settings):
    settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET = "rzp_test_key", "secret"
    settings.RAZORPAYX_ACCOUNT_NUMBER = "2323230000000000"
    calls, replies = [], []

    def request(method, url, json=None, params=None, headers=None, auth=None, timeout=None):
        calls.append(
            {
                "method": method,
                "url": url,
                "json": json,
                "params": dict(params or {}),
                "headers": headers or {},
            }
        )
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(requests, "request", request)
    return calls, replies


def test_contacts_fund_accounts_and_validation(http):
    calls, replies = http
    x = RazorpayXProvider()
    replies += [
        Response(200, {"id": "cont_1"}),
        Response(200, {"id": "fa_1"}),
        Response(200, {"id": "fa_2"}),
        Response(200, {"id": "fav_1", "status": "created"}),
        Response(
            200, {"id": "fav_1", "status": "completed", "results": {"account_status": "active"}}
        ),
        Response(
            200, {"id": "fav_2", "status": "failed", "status_details": {"description": "Bank down"}}
        ),
        Response(200, {}),
    ]
    assert x.create_contact(name="Asha", reference="t1") == "cont_1"
    assert x.create_fund_account(contact_id="cont_1", vpa="asha@okicici") == "fa_1"
    assert calls[1]["json"]["vpa"] == {"address": "asha@okicici"}
    bank = BankDetails("Asha Rao", "123456789012", "HDFC0001234")
    assert x.create_fund_account(contact_id="cont_1", bank=bank) == "fa_2"
    assert calls[2]["json"]["bank_account"]["ifsc"] == "HDFC0001234"
    assert x.validate(fund_account_id="fa_1", reference="r").status == "pending"
    assert calls[3]["json"]["account_number"] == "2323230000000000"
    assert x.get_validation("fav_1").status == "verified"
    failed = x.get_validation("fav_2")
    assert (failed.status, failed.reason) == ("failed", "Bank down")
    x.deactivate_fund_account("fa_1")
    assert calls[-1]["method"] == "PATCH" and calls[-1]["json"] == {"active": False}


def test_payouts_carry_an_idempotency_key(http):
    calls, replies = http
    replies.append(Response(200, {"id": "pout_1", "status": "processing", "utr": None}))
    result = RazorpayXProvider().create_payout(
        fund_account_id="fa_1",
        amount_paise=447_800,
        method="bank",
        idempotency_key="k1",
        reference="p1",
        narration="Barterly stipend",
    )
    assert (result.id, result.status, result.utr) == ("pout_1", "processing", "")
    assert calls[0]["headers"] == {"X-Payout-Idempotency": "k1"}
    assert calls[0]["json"]["mode"] == "IMPS" and calls[0]["json"]["amount"] == 447_800


def test_errors_become_gateway_errors(http, settings):
    _, replies = http
    replies += [
        Response(400, {"error": {"description": "Insufficient balance"}}),
        requests.Timeout(),
    ]
    with pytest.raises(GatewayError, match="Insufficient balance"):
        RazorpayXProvider().create_contact(name="a", reference="b")
    with pytest.raises(GatewayError, match="couldn't reach"):
        RazorpayXProvider().create_contact(name="a", reference="b")
    settings.RAZORPAY_KEY_ID = ""
    with pytest.raises(GatewayError, match="aren't configured"):
        RazorpayXProvider().create_contact(name="a", reference="b")


def test_day_total_counts_payouts_that_went_out(http):
    calls, replies = http
    page = [{"amount": 10, "status": "processed"}] * 100
    replies += [
        Response(200, {"items": page}),
        Response(
            200, {"items": [{"amount": 5, "status": "reversed"}, {"amount": 7, "status": "queued"}]}
        ),
    ]
    assert RazorpayXProvider().day_total(date(2026, 11, 18)) == 1_007
    assert calls[1]["params"]["skip"] == 100


def test_webhooks_are_verified(settings):
    settings.RAZORPAYX_WEBHOOK_SECRET = "x-secret"  # noqa: S105
    body = b'{"event": "payout.processed", "payload": {"payout": {"entity": {"id": "p"}}}}'
    headers = {"X-Razorpay-Signature": signature(body, "x-secret"), "X-Razorpay-Event-Id": "e"}
    event = RazorpayXProvider().parse_webhook(body, headers)
    assert (event.event, event.payout) == ("payout.processed", {"id": "p"})
    with pytest.raises(GatewayError, match="signature"):
        RazorpayXProvider().parse_webhook(body, {**headers, "X-Razorpay-Signature": "x"})
    with pytest.raises(GatewayError, match="event id"):
        RazorpayXProvider().parse_webhook(body, {**headers, "X-Razorpay-Event-Id": ""})
