"""Razorpay Subscriptions over its REST API (https://razorpay.com/docs/api/payments/subscriptions/).

Keys come from the environment (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
RAZORPAY_WEBHOOK_SECRET; Secret Manager in deployed environments). Plans are created
in the Razorpay dashboard with the price including GST; their ids go on Plan rows.
Webhooks are signed: X-Razorpay-Signature is the HMAC-SHA256 of the raw body with the
webhook secret.
"""

import hashlib
import hmac
import json

import requests
from django.conf import settings

from apps.billing.gateway.base import GatewayError, GatewaySubscription, WebhookEvent

API = "https://api.razorpay.com/v1"
# Months a subscription runs before it completes (Razorpay needs an end).
TOTAL_MONTHS = 120
TIMEOUT = 15


def signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class RazorpayGateway:
    name = "razorpay"

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise GatewayError("Payments aren't configured here.")
        try:
            response = requests.request(
                method,
                f"{API}{path}",
                json=payload,
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

    def create_subscription(self, *, plan_id, start_at, notes) -> GatewaySubscription:
        payload = {
            "plan_id": plan_id,
            "total_count": TOTAL_MONTHS,
            "quantity": 1,
            "customer_notify": 1,
            "notes": {k: str(v) for k, v in notes.items()},
        }
        if start_at is not None:
            payload["start_at"] = int(start_at.timestamp())
        data = self._call("POST", "/subscriptions", payload)
        return GatewaySubscription(
            id=data["id"],
            status=data.get("status", "created"),
            checkout_url=data.get("short_url", ""),
        )

    def change_plan(self, subscription_id, *, plan_id, at_cycle_end) -> None:
        self._call(
            "PATCH",
            f"/subscriptions/{subscription_id}",
            {"plan_id": plan_id, "schedule_change_at": "cycle_end" if at_cycle_end else "now"},
        )

    def cancel(self, subscription_id, *, at_cycle_end) -> None:
        self._call(
            "POST",
            f"/subscriptions/{subscription_id}/cancel",
            {"cancel_at_cycle_end": 1 if at_cycle_end else 0},
        )

    def parse_webhook(self, body: bytes, headers) -> WebhookEvent:
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        given = headers.get("X-Razorpay-Signature", "")
        if not secret or not given or not hmac.compare_digest(signature(body, secret), given):
            raise GatewayError("Bad webhook signature.")
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise GatewayError("The webhook body isn't JSON.") from exc
        payload = data.get("payload") or {}
        event_id = headers.get("X-Razorpay-Event-Id", "") or (
            f"{data.get('event')}:{data.get('created_at')}:"
            f"{(payload.get('payment') or {}).get('entity', {}).get('id', '')}"
        )
        return WebhookEvent(
            event_id=event_id,
            event=data.get("event", ""),
            subscription=(payload.get("subscription") or {}).get("entity") or {},
            payment=(payload.get("payment") or {}).get("entity") or {},
            raw=data,
        )
