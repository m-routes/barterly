"""The payment gateway interface. Razorpay Subscriptions today (razorpay.py); tests and
local runs use the fake (fake.py). Chosen by settings.BILLING_GATEWAY.

The gateway owns cards, charges and retries; Barterly keeps its own copy of each
subscription's state from the gateway's webhooks (apps.billing.services).
"""

from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


class GatewayError(Exception):
    """The gateway refused or couldn't be reached (the message says which)."""


@dataclass(frozen=True)
class GatewaySubscription:
    id: str
    status: str
    checkout_url: str = ""


@dataclass(frozen=True)
class WebhookEvent:
    """A verified webhook, parsed. `subscription` and `payment` are the gateway's
    entities (dicts) when the event carries them."""

    event_id: str
    event: str
    subscription: dict = field(default_factory=dict)
    payment: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


class PaymentGateway(Protocol):
    name: str

    def create_subscription(
        self, *, plan_id: str, start_at: datetime | None, notes: dict
    ) -> GatewaySubscription:
        """A subscription waiting for the vendor to pay at the hosted checkout. With
        `start_at` (a trial), the card is set up now and the first charge waits."""
        ...

    def change_plan(self, subscription_id: str, *, plan_id: str, at_cycle_end: bool) -> None: ...

    def cancel(self, subscription_id: str, *, at_cycle_end: bool) -> None: ...

    def parse_webhook(self, body: bytes, headers) -> WebhookEvent:
        """Check the signature (raise GatewayError if it's wrong) and parse."""
        ...


@cache
def _build(path: str) -> PaymentGateway:
    return import_string(path)()


def get_gateway() -> PaymentGateway:
    return _build(settings.BILLING_GATEWAY)
