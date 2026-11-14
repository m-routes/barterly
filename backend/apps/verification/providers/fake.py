"""A KYC provider for tests and local development. It checks nothing.

Webhooks are signed the way most providers do it, so the real verification path runs:

    X-Kyc-Timestamp: <unix seconds>
    X-Kyc-Signature: hex HMAC-SHA256(KYC_WEBHOOK_SECRET, "<timestamp>.<raw body>")
    Idempotency-Key: <unique per event>

Locally, finish a check with `manage.py fake_kyc_result <reference> approved`.
"""

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Mapping

from django.conf import settings

from apps.verification.providers.base import (
    InvalidWebhook,
    KycOutcome,
    KycResult,
    KycSession,
    KycWebhook,
)

SIGNATURE_HEADER = "X-Kyc-Signature"
TIMESTAMP_HEADER = "X-Kyc-Timestamp"
IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_SKEW_SECONDS = 300


def sign(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _header(headers: Mapping[str, str], name: str) -> str:
    lowered = {key.lower(): value for key, value in headers.items()}
    return lowered.get(name.lower(), "")


class FakeKycProvider:
    name = "fake"

    def __init__(self) -> None:
        self.results: dict[str, KycResult] = {}

    def start_check(self, *, case_id: str, user_id: str, document_type: str) -> KycSession:
        reference = f"fake_{uuid.uuid4().hex}"
        self.results[reference] = KycResult(reference=reference, outcome=KycOutcome.PENDING)
        return KycSession(
            reference=reference,
            client_token=f"fake-token-{uuid.uuid4().hex[:12]}",
            redirect_url=f"https://kyc.invalid/fake/{reference}",
            expires_in_seconds=1800,
        )

    def get_result(self, reference: str) -> KycResult:
        return self.results.get(
            reference, KycResult(reference=reference, outcome=KycOutcome.PENDING)
        )

    def set_result(self, result: KycResult) -> None:
        self.results[result.reference] = result

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> KycWebhook:
        secret = settings.KYC_WEBHOOK_SECRET
        if not secret:
            raise InvalidWebhook("No webhook secret is configured.")
        timestamp = _header(headers, TIMESTAMP_HEADER)
        signature = _header(headers, SIGNATURE_HEADER)
        key = _header(headers, IDEMPOTENCY_HEADER)
        if not (timestamp.isdigit() and signature and key):
            raise InvalidWebhook("Missing signature, timestamp or idempotency key.")
        if abs(time.time() - int(timestamp)) > MAX_SKEW_SECONDS:
            raise InvalidWebhook("Timestamp too old or in the future.")
        if not hmac.compare_digest(sign(secret, timestamp, body), signature):
            raise InvalidWebhook("Bad signature.")
        try:
            data = json.loads(body)
            result = KycResult(
                reference=str(data["reference"]),
                outcome=KycOutcome(data["outcome"]).value,
                reason=str(data.get("reason", ""))[:500],
                id_last_four=str(data.get("id_last_four", ""))[-4:],
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidWebhook(f"Malformed body: {exc}") from exc
        return KycWebhook(idempotency_key=key[:128], result=result)

    @staticmethod
    def webhook_request(
        result: KycResult, *, key: str | None = None, timestamp: int | None = None
    ) -> tuple[bytes, dict[str, str]]:
        """A signed delivery as the provider would send it (for tests and the command)."""
        body = json.dumps(
            {
                "reference": result.reference,
                "outcome": result.outcome,
                "reason": result.reason,
                "id_last_four": result.id_last_four,
            }
        ).encode()
        ts = str(int(time.time()) if timestamp is None else timestamp)
        headers = {
            TIMESTAMP_HEADER: ts,
            SIGNATURE_HEADER: sign(settings.KYC_WEBHOOK_SECRET, ts, body),
            IDEMPOTENCY_HEADER: key or uuid.uuid4().hex,
        }
        return body, headers
