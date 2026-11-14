"""The KYC provider interface.

A provider runs the ID-plus-selfie check: the app hands the user to the provider's SDK
or hosted page with the session from start_check(), the provider compares the selfie
with the ID, and reports back through a signed webhook (or get_result() when polled).
We only ever receive the provider's reference, the outcome and the ID's last four
characters; images and full numbers stay with the provider.

The class is a code setting (KYC_PROVIDER), so a deployed service can't be pointed at
the fake from the environment.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import Protocol

from django.conf import settings
from django.db import models
from django.utils.module_loading import import_string


class KycOutcome(models.TextChoices):
    PENDING = "pending", "Still checking"
    MANUAL_REVIEW = "manual_review", "Provider wants a human to look"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


@dataclass(frozen=True)
class KycSession:
    """What the client needs to run the provider's capture flow."""

    reference: str
    client_token: str
    redirect_url: str
    expires_in_seconds: int


@dataclass(frozen=True)
class KycResult:
    reference: str
    outcome: str  # a KycOutcome value
    reason: str = ""
    id_last_four: str = ""


@dataclass(frozen=True)
class KycWebhook:
    """A verified webhook delivery."""

    idempotency_key: str
    result: KycResult


class KycProviderNotConfigured(Exception):
    """No real provider is wired up for this environment."""


class KycProviderError(Exception):
    """The provider failed or could not be reached."""


class InvalidWebhook(Exception):
    """Bad signature, stale timestamp or malformed body. Respond 401/400; never process."""


class KycProvider(Protocol):
    name: str

    def start_check(self, *, case_id: str, user_id: str, document_type: str) -> KycSession:
        """Open a capture session for one ID document plus a selfie."""
        ...

    def get_result(self, reference: str) -> KycResult:
        """Ask the provider for the current outcome (for missed webhooks)."""
        ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> KycWebhook:
        """Check the signature over the raw body and parse it. Raises InvalidWebhook."""
        ...


@cache
def _build(path: str) -> KycProvider:
    return import_string(path)()


def get_kyc_provider() -> KycProvider:
    return _build(settings.KYC_PROVIDER)
