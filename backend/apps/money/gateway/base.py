"""The escrow payment gateway: take the host's payment into the platform's gateway
account, transfer payouts to talent, refund hosts, and report a day's totals for
reconciliation. Razorpay Route today (route.py); chosen by settings.ESCROW_GATEWAY.

LEGAL REVIEW NEEDED: the fund-flow structure (Route linked accounts, a nodal/escrow
account, or another arrangement) must be the one your lawyer approves before launch.
Only the implementation behind this interface would change.
"""

from dataclasses import dataclass, field
from datetime import date
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


class GatewayError(Exception):
    """The gateway refused or couldn't be reached."""


@dataclass(frozen=True)
class Order:
    id: str
    amount_paise: int
    currency: str = "INR"


@dataclass(frozen=True)
class GatewayEventData:
    """A verified webhook. The entity dicts are the gateway's own."""

    event_id: str
    event: str
    payment: dict = field(default_factory=dict)
    refund: dict = field(default_factory=dict)
    transfer: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DayTotals:
    """What the gateway says happened on one day, in paise."""

    captured: int = 0
    refunded: int = 0
    transferred: int = 0
    fees: int = 0


class EscrowGateway(Protocol):
    name: str

    def create_order(self, *, amount_paise: int, receipt: str, notes: dict) -> Order: ...

    def transfer(self, *, account_id: str, amount_paise: int, notes: dict) -> str:
        """Pay a talent's linked account from the platform balance; returns its id."""
        ...

    def refund(self, *, payment_id: str, amount_paise: int, notes: dict) -> str: ...

    def parse_webhook(self, body: bytes, headers) -> GatewayEventData: ...

    def day_totals(self, day: date) -> DayTotals: ...


@cache
def _build(path: str) -> EscrowGateway:
    return import_string(path)()


def get_gateway() -> EscrowGateway:
    return _build(settings.ESCROW_GATEWAY)
