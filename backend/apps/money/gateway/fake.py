"""A gateway for tests and local runs: remembers calls, reports the totals it's told,
and signs webhooks the way Razorpay does."""

import itertools
import json

from apps.money.gateway.base import DayTotals, GatewayError, Order
from apps.money.gateway.route import RazorpayRouteGateway, signature

_ids = itertools.count(1)


class FakeEscrowGateway(RazorpayRouteGateway):
    calls: list[tuple] = []
    fail_next: list[Exception] = []
    totals: dict = {}

    def _maybe_fail(self) -> None:
        if FakeEscrowGateway.fail_next:
            raise FakeEscrowGateway.fail_next.pop(0)

    def create_order(self, *, amount_paise, receipt, notes) -> Order:
        self._maybe_fail()
        FakeEscrowGateway.calls.append(("order", amount_paise, receipt))
        return Order(id=f"order_fake{next(_ids)}", amount_paise=amount_paise)

    def transfer(self, *, account_id, amount_paise, notes) -> str:
        self._maybe_fail()
        FakeEscrowGateway.calls.append(("transfer", account_id, amount_paise))
        return f"trf_fake{next(_ids)}"

    def refund(self, *, payment_id, amount_paise, notes) -> str:
        self._maybe_fail()
        if not payment_id:
            raise GatewayError("No payment to refund.")
        FakeEscrowGateway.calls.append(("refund", payment_id, amount_paise))
        return f"rfnd_fake{next(_ids)}"

    def day_totals(self, day) -> DayTotals:
        self._maybe_fail()
        return FakeEscrowGateway.totals.get(day, DayTotals())

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.fail_next = []
        cls.totals = {}


def signed(event: dict, secret: str, event_id: str) -> tuple[bytes, dict]:
    body = json.dumps(event).encode()
    return body, {"X-Razorpay-Signature": signature(body, secret), "X-Razorpay-Event-Id": event_id}
