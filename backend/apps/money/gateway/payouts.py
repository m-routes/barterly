"""The payout provider: contacts, fund accounts (UPI or bank), account validation,
and payouts. RazorpayX today; chosen by settings.PAYOUT_PROVIDER.

LEGAL REVIEW NEEDED: payouts leave from the platform's RazorpayX account, which must be
funded from the payment-gateway settlement. The structure (and any nodal or escrow
account it needs) must be the one your lawyer approves.

Account numbers and UPI ids pass through to the provider and are never stored here.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import cache
from typing import Protocol
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.utils.module_loading import import_string

from apps.money.gateway.base import GatewayError

API = "https://api.razorpay.com/v1"
IST = ZoneInfo("Asia/Kolkata")
TIMEOUT = 15


@dataclass(frozen=True)
class BankDetails:
    holder_name: str
    account_number: str
    ifsc: str


@dataclass(frozen=True)
class Validation:
    id: str
    status: str  # "pending", "verified" or "failed"
    reason: str = ""


@dataclass(frozen=True)
class ProviderPayout:
    id: str
    status: str  # the provider's: queued, pending, processing, processed, reversed, ...
    utr: str = ""
    reason: str = ""


@dataclass(frozen=True)
class PayoutEvent:
    event_id: str
    event: str
    payout: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


class PayoutProvider(Protocol):
    def create_contact(self, *, name: str, reference: str) -> str: ...

    def create_fund_account(
        self, *, contact_id: str, vpa: str = "", bank: BankDetails | None = None
    ) -> str: ...

    def deactivate_fund_account(self, fund_account_id: str) -> None: ...

    def validate(self, *, fund_account_id: str, reference: str) -> Validation: ...

    def get_validation(self, validation_id: str) -> Validation: ...

    def create_payout(
        self,
        *,
        fund_account_id: str,
        amount_paise: int,
        method: str,
        idempotency_key: str,
        reference: str,
        narration: str,
    ) -> ProviderPayout: ...

    def parse_webhook(self, body: bytes, headers) -> PayoutEvent: ...

    def day_total(self, day: date) -> int:
        """Paise paid out (not failed or reversed) on that India day."""
        ...


@cache
def _build(path: str) -> PayoutProvider:
    return import_string(path)()


def get_provider() -> PayoutProvider:
    return _build(settings.PAYOUT_PROVIDER)


def signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# The provider's payout states, as ours.
DONE, FAILED_STATES = "processed", ("failed", "rejected", "cancelled")


def validation_from(data: dict) -> Validation:
    status = data.get("status", "")
    results = data.get("results") or {}
    if status == "completed":
        if results.get("account_status") == "active":
            return Validation(data["id"], "verified")
        return Validation(data["id"], "failed", "The bank says this account isn't active.")
    if status == "failed":
        reason = (data.get("status_details") or {}).get("description") or "The check failed."
        return Validation(data["id"], "failed", reason)
    return Validation(data["id"], "pending")


class RazorpayXProvider:
    def _call(self, method: str, path: str, payload=None, params=None, headers=None) -> dict:
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise GatewayError("Payouts aren't configured here.")
        try:
            response = requests.request(
                method,
                f"{API}{path}",
                json=payload,
                params=params,
                headers=headers,
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise GatewayError("We couldn't reach the payout provider.") from exc
        if response.status_code >= 400:
            try:
                message = response.json()["error"]["description"]
            except (ValueError, KeyError, TypeError):
                message = f"HTTP {response.status_code}"
            raise GatewayError(f"The payout provider said: {message}")
        return response.json()

    def create_contact(self, *, name, reference) -> str:
        data = self._call(
            "POST", "/contacts", {"name": name[:50], "type": "vendor", "reference_id": reference}
        )
        return data["id"]

    def create_fund_account(self, *, contact_id, vpa="", bank=None) -> str:
        if vpa:
            payload = {"contact_id": contact_id, "account_type": "vpa", "vpa": {"address": vpa}}
        else:
            payload = {
                "contact_id": contact_id,
                "account_type": "bank_account",
                "bank_account": {
                    "name": bank.holder_name,
                    "ifsc": bank.ifsc,
                    "account_number": bank.account_number,
                },
            }
        return self._call("POST", "/fund_accounts", payload)["id"]

    def deactivate_fund_account(self, fund_account_id) -> None:
        self._call("PATCH", f"/fund_accounts/{fund_account_id}", {"active": False})

    def validate(self, *, fund_account_id, reference) -> Validation:
        data = self._call(
            "POST",
            "/fund_accounts/validations",
            {
                "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER,
                "fund_account": {"id": fund_account_id},
                "amount": 100,  # ₹1, deposited to the account being checked
                "currency": "INR",
                "notes": {"reference": reference},
            },
        )
        return validation_from(data)

    def get_validation(self, validation_id) -> Validation:
        return validation_from(self._call("GET", f"/fund_accounts/validations/{validation_id}"))

    def create_payout(
        self, *, fund_account_id, amount_paise, method, idempotency_key, reference, narration
    ) -> ProviderPayout:
        data = self._call(
            "POST",
            "/payouts",
            {
                "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER,
                "fund_account_id": fund_account_id,
                "amount": amount_paise,
                "currency": "INR",
                "mode": "UPI" if method == "upi" else "IMPS",
                "purpose": "payout",
                "queue_if_low_balance": True,
                "reference_id": reference[:40],
                "narration": narration[:30],
            },
            headers={"X-Payout-Idempotency": idempotency_key},
        )
        return payout_from(data)

    def parse_webhook(self, body, headers) -> PayoutEvent:
        secret = settings.RAZORPAYX_WEBHOOK_SECRET
        given = headers.get("X-Razorpay-Signature", "")
        if not secret or not given or not hmac.compare_digest(signature(body, secret), given):
            raise GatewayError("Bad webhook signature.")
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise GatewayError("The webhook body isn't JSON.") from exc
        event_id = headers.get("X-Razorpay-Event-Id", "")
        if not event_id:
            raise GatewayError("The webhook has no event id.")
        payload = data.get("payload") or {}

        def entity(name: str) -> dict:
            return (payload.get(name) or {}).get("entity") or {}

        return PayoutEvent(
            event_id=event_id,
            event=data.get("event", ""),
            payout=entity("payout"),
            validation=entity("fund_account.validation") or entity("fund_account_validation"),
            raw=data,
        )

    def day_total(self, day) -> int:
        start = datetime.combine(day, time.min, tzinfo=IST)
        params = {
            "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER,
            "from": int(start.timestamp()),
            "to": int((start + timedelta(days=1)).timestamp()) - 1,
            "count": 100,
            "skip": 0,
        }
        total = 0
        while True:
            page = self._call("GET", "/payouts", params=params).get("items", [])
            total += sum(
                int(p["amount"])
                for p in page
                if p.get("status") in ("processed", "processing", "queued", "pending")
            )
            if len(page) < params["count"]:
                return total
            params["skip"] += params["count"]


def payout_from(data: dict) -> ProviderPayout:
    details = data.get("status_details") or {}
    return ProviderPayout(
        id=data["id"],
        status=data.get("status", ""),
        utr=data.get("utr") or "",
        reason=details.get("description") or data.get("failure_reason") or "",
    )
