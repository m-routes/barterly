"""Placeholder for the real KYC provider. Every call says it isn't configured (HTTP 503).

To wire one up (e.g. a DigiLocker / video-KYC vendor):

1. Write a class here with `name`, `start_check`, `get_result` and `verify_webhook`
   (see providers/base.py for the contract). Call the vendor's API with an HTTP
   timeout; raise KycProviderError when it fails.
2. Map the vendor's statuses onto KycOutcome. Keep only the reference, the outcome, a
   short reason and the ID's last four characters. Never store images or full numbers.
3. verify_webhook: check the vendor's signature over the raw body with a constant-time
   compare, reject stale timestamps, and use the vendor's event id as the idempotency key.
4. Put the API key and webhook secret in Secret Manager (KYC_API_KEY,
   KYC_WEBHOOK_SECRET), never in code.
5. Point settings.KYC_PROVIDER at the class and register the webhook URL
   /api/v1/verification/webhooks/kyc/ with the vendor.
"""

from collections.abc import Mapping

from apps.verification.providers.base import (
    KycProviderNotConfigured,
    KycResult,
    KycSession,
    KycWebhook,
)

MESSAGE = "No KYC provider is configured for this environment."


class ExternalKycProvider:
    name = "external"

    def start_check(self, *, case_id: str, user_id: str, document_type: str) -> KycSession:
        raise KycProviderNotConfigured(MESSAGE)

    def get_result(self, reference: str) -> KycResult:
        raise KycProviderNotConfigured(MESSAGE)

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> KycWebhook:
        raise KycProviderNotConfigured(MESSAGE)
