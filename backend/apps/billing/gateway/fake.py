"""A gateway for tests and local runs: remembers calls, and signs webhooks the same
way Razorpay does (with settings.RAZORPAY_WEBHOOK_SECRET)."""

import itertools
import json

from apps.billing.gateway.base import GatewayError, GatewaySubscription
from apps.billing.gateway.razorpay import RazorpayGateway, signature

_ids = itertools.count(1)


class FakeGateway(RazorpayGateway):
    name = "razorpay"
    calls: list[tuple] = []
    fail_next: list[Exception] = []

    def _maybe_fail(self) -> None:
        if FakeGateway.fail_next:
            raise FakeGateway.fail_next.pop(0)

    def create_subscription(self, *, plan_id, start_at, notes) -> GatewaySubscription:
        self._maybe_fail()
        if not plan_id:
            raise GatewayError("This plan has no Razorpay plan id.")
        sub_id = f"sub_fake{next(_ids)}"
        FakeGateway.calls.append(("create", plan_id, start_at, dict(notes)))
        return GatewaySubscription(
            id=sub_id, status="created", checkout_url=f"https://rzp.test/checkout/{sub_id}"
        )

    def change_plan(self, subscription_id, *, plan_id, at_cycle_end) -> None:
        self._maybe_fail()
        FakeGateway.calls.append(("change", subscription_id, plan_id, at_cycle_end))

    def cancel(self, subscription_id, *, at_cycle_end) -> None:
        self._maybe_fail()
        FakeGateway.calls.append(("cancel", subscription_id, at_cycle_end))

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.fail_next = []


def signed(event: dict, secret: str, event_id: str) -> tuple[bytes, dict]:
    """A webhook body and headers as Razorpay would send them."""
    body = json.dumps(event).encode()
    return body, {"X-Razorpay-Signature": signature(body, secret), "X-Razorpay-Event-Id": event_id}
