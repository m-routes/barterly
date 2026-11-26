"""A gateway for tests and local runs: remembers calls, reports the totals it's told,
and signs webhooks the way Razorpay does."""

import itertools
import json

from apps.money.gateway.base import DayTotals, GatewayError, Order
from apps.money.gateway.payouts import ProviderPayout, Validation
from apps.money.gateway.payouts import RazorpayXProvider as RazorpayXProvider_
from apps.money.gateway.payouts import signature as x_signature
from apps.money.gateway.razorpay import RazorpayEscrowGateway, signature

_ids = itertools.count(1)


class FakeEscrowGateway(RazorpayEscrowGateway):
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


class FakePayoutProvider(RazorpayXProvider_):
    """Remembers calls; validations stay pending until a test settles them (or set
    `validate_as`); payouts are accepted as `processing`."""

    calls: list[tuple] = []
    fail_next: list[Exception] = []
    validate_as: str = "pending"
    validations: dict = {}
    payouts_by_key: dict = {}
    totals: dict = {}

    def _maybe_fail(self) -> None:
        if FakePayoutProvider.fail_next:
            raise FakePayoutProvider.fail_next.pop(0)

    def create_contact(self, *, name, reference):
        self._maybe_fail()
        FakePayoutProvider.calls.append(("contact", reference))
        return f"cont_fake{next(_ids)}"

    def create_fund_account(self, *, contact_id, vpa="", bank=None):
        self._maybe_fail()
        FakePayoutProvider.calls.append(("fund_account", contact_id, vpa or bank.account_number))
        return f"fa_fake{next(_ids)}"

    def deactivate_fund_account(self, fund_account_id):
        FakePayoutProvider.calls.append(("deactivate", fund_account_id))

    def validate(self, *, fund_account_id, reference):
        self._maybe_fail()
        validation = Validation(
            f"fav_fake{next(_ids)}",
            FakePayoutProvider.validate_as,
            "" if FakePayoutProvider.validate_as != "failed" else "Invalid",
        )
        FakePayoutProvider.validations[validation.id] = validation
        FakePayoutProvider.calls.append(("validate", fund_account_id))
        return validation

    def get_validation(self, validation_id):
        self._maybe_fail()
        return FakePayoutProvider.validations[validation_id]

    def create_payout(
        self, *, fund_account_id, amount_paise, method, idempotency_key, reference, narration
    ):
        self._maybe_fail()
        # Like the real one: the same idempotency key returns the same payout.
        if idempotency_key in FakePayoutProvider.payouts_by_key:
            return FakePayoutProvider.payouts_by_key[idempotency_key]
        FakePayoutProvider.calls.append(("payout", fund_account_id, amount_paise, method))
        payout = ProviderPayout(f"pout_fake{next(_ids)}", "processing")
        FakePayoutProvider.payouts_by_key[idempotency_key] = payout
        return payout

    def day_total(self, day):
        self._maybe_fail()
        return FakePayoutProvider.totals.get(day, 0)

    @classmethod
    def reset(cls) -> None:
        cls.calls, cls.fail_next, cls.validations = [], [], {}
        cls.payouts_by_key, cls.totals, cls.validate_as = {}, {}, "pending"


def signed_x(event: dict, secret: str, event_id: str) -> tuple[bytes, dict]:
    body = json.dumps(event).encode()
    return body, {
        "X-Razorpay-Signature": x_signature(body, secret),
        "X-Razorpay-Event-Id": event_id,
    }
