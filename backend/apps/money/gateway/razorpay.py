"""Razorpay Orders and refunds over the REST API.

The host pays a Razorpay order at checkout (captured automatically); money sits in the
platform's Razorpay balance until it's released and paid out (gateway/payouts.py).
Webhooks are signed like Razorpay's others: X-Razorpay-Signature is the HMAC-SHA256 of
the body with RAZORPAY_ESCROW_WEBHOOK_SECRET.
"""

import hashlib
import hmac
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests
from django.conf import settings

from apps.money.gateway.base import DayTotals, GatewayError, GatewayEventData, Order

API = "https://api.razorpay.com/v1"
IST = ZoneInfo("Asia/Kolkata")
TIMEOUT = 15


def signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class RazorpayEscrowGateway:
    name = "razorpay"

    def _call(self, method: str, path: str, payload: dict | None = None, params=None) -> dict:
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise GatewayError("Payments aren't configured here.")
        try:
            response = requests.request(
                method,
                f"{API}{path}",
                json=payload,
                params=params,
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise GatewayError("We couldn't reach the payment provider.") from exc
        if response.status_code >= 400:
            try:
                message = response.json()["error"]["description"]
            except (ValueError, KeyError, TypeError):
                message = f"HTTP {response.status_code}"
            raise GatewayError(f"The payment provider said: {message}")
        return response.json()

    def create_order(self, *, amount_paise, receipt, notes) -> Order:
        data = self._call(
            "POST",
            "/orders",
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt[:40],
                "payment_capture": 1,
                "notes": {k: str(v) for k, v in notes.items()},
            },
        )
        return Order(id=data["id"], amount_paise=int(data["amount"]))

    def refund(self, *, payment_id, amount_paise, notes) -> str:
        data = self._call(
            "POST",
            f"/payments/{payment_id}/refund",
            {"amount": amount_paise, "notes": {k: str(v) for k, v in notes.items()}},
        )
        return data["id"]

    def parse_webhook(self, body: bytes, headers) -> GatewayEventData:
        secret = settings.RAZORPAY_ESCROW_WEBHOOK_SECRET
        given = headers.get("X-Razorpay-Signature", "")
        if not secret or not given or not hmac.compare_digest(signature(body, secret), given):
            raise GatewayError("Bad webhook signature.")
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise GatewayError("The webhook body isn't JSON.") from exc
        payload = data.get("payload") or {}

        def entity(name: str) -> dict:
            return (payload.get(name) or {}).get("entity") or {}

        event_id = headers.get("X-Razorpay-Event-Id", "")
        if not event_id:
            raise GatewayError("The webhook has no event id.")
        return GatewayEventData(
            event_id=event_id,
            event=data.get("event", ""),
            payment=entity("payment"),
            refund=entity("refund"),
            raw=data,
        )

    def _all(self, path: str, day) -> list[dict]:
        start = datetime.combine(day, time.min, tzinfo=IST)
        params = {
            "from": int(start.timestamp()),
            "to": int((start + timedelta(days=1)).timestamp()) - 1,
            "count": 100,
            "skip": 0,
        }
        items: list[dict] = []
        while True:
            page = self._call("GET", path, params=params).get("items", [])
            items.extend(page)
            if len(page) < params["count"]:
                return items
            params["skip"] += params["count"]

    def day_totals(self, day) -> DayTotals:
        payments = [
            p for p in self._all("/payments", day) if p.get("status") in ("captured", "refunded")
        ]
        refunds = [r for r in self._all("/refunds", day) if r.get("status") == "processed"]
        return DayTotals(
            captured=sum(int(p["amount"]) for p in payments),
            refunded=sum(int(r["amount"]) for r in refunds),
            fees=sum(int(p.get("fee") or 0) for p in payments),
        )
