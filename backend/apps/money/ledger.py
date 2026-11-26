"""Posting money movements, and the integer arithmetic they use.

post() is the only way money moves. It writes one LedgerTransaction and its lines in
one database transaction. Each line debits one account and credits another for the
same whole-paise amount, so a movement always balances. The idempotency key makes a
repeat post (a retried webhook, a job run twice) return the movement already made,
after checking it's the same movement; a different movement under the same key is an
error, never a silent overwrite.

No floats: amounts are ints (bools refused), percentages are basis points, and rupee
strings are parsed with Decimal and converted exactly.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.money.models import Account, AccountKind, LedgerEntry, LedgerTransaction

# The chart of accounts (seeded by migration 0003).
GATEWAY = "gateway:clearing"  # money at the gateway (asset)
ESCROW = "escrow:held"  # stipends held for bookings (liability)
TALENT = "talent:payable"  # owed to talent, before the transfer (liability)
COMMISSION = "revenue:commission"
FEE_RECOVERY = "revenue:fee_recovery"  # the gateway fee the host pays
GST_OUTPUT = "tax:gst_output"  # GST collected (liability)
GST_INPUT = "tax:gst_input"  # GST paid on the gateway's fee (asset)
TDS = "tax:tds_payable"  # TDS withheld (liability)
GATEWAY_FEES = "expense:gateway_fees"
ADJUSTMENTS = "equity:adjustments"

ACCOUNTS = {
    GATEWAY: ("Gateway clearing", AccountKind.ASSET),
    ESCROW: ("Escrow held for bookings", AccountKind.LIABILITY),
    TALENT: ("Payable to talent", AccountKind.LIABILITY),
    COMMISSION: ("Commission", AccountKind.REVENUE),
    FEE_RECOVERY: ("Gateway fee recovered from hosts", AccountKind.REVENUE),
    GST_OUTPUT: ("GST output", AccountKind.LIABILITY),
    GST_INPUT: ("GST input credit", AccountKind.ASSET),
    TDS: ("TDS payable", AccountKind.LIABILITY),
    GATEWAY_FEES: ("Gateway fees", AccountKind.EXPENSE),
    ADJUSTMENTS: ("Adjustments", AccountKind.EQUITY),
}


class LedgerError(Exception):
    """A movement that can't be posted (bad amount, unknown account, key reused)."""


# ---------- Integer arithmetic ----------


def check_paise(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise LedgerError(f"Amounts are whole paise (int), not {type(value).__name__}.")
    return value


def share(amount_paise: int, basis_points: int) -> int:
    """amount x bps / 10,000, rounded half up, in integer arithmetic."""
    check_paise(amount_paise)
    check_paise(basis_points)
    if amount_paise < 0 or basis_points < 0:
        raise LedgerError("Shares are of non-negative amounts.")
    return (amount_paise * basis_points + 5_000) // 10_000


def rupees_to_paise(value: str) -> int:
    """'5000.00' → 500000. Exact (Decimal from the string), never via a float."""
    if isinstance(value, float):
        raise LedgerError("Rupee amounts come as strings, never floats.")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise LedgerError(f"Not an amount: {value!r}.") from exc
    paise = amount * 100
    if paise != paise.to_integral_value():
        raise LedgerError(f"{value!r} has fractions of a paisa.")
    return int(paise)


# ---------- Posting ----------


@dataclass(frozen=True)
class Line:
    debit: str
    credit: str
    amount: int


def post(
    kind: str,
    key: str,
    lines: list[Line],
    *,
    booking=None,
    reference: str = "",
    memo: str = "",
    now=None,
) -> LedgerTransaction:
    """Post one balanced movement, once. Joins the caller's database transaction."""
    if not lines:
        raise LedgerError("A movement needs at least one line.")
    for line in lines:
        check_paise(line.amount)
        if line.amount <= 0:
            raise LedgerError("Every line moves a positive amount.")
        if line.debit == line.credit:
            raise LedgerError("A line moves money between two different accounts.")
    codes = {code for line in lines for code in (line.debit, line.credit)}
    accounts = {a.code: a for a in Account.objects.filter(code__in=codes)}
    missing = codes - set(accounts)
    if missing:
        raise LedgerError(f"Unknown accounts: {', '.join(sorted(missing))}.")

    existing = LedgerTransaction.objects.filter(idempotency_key=key).first()
    if existing:
        _same_or_fail(existing, kind, lines)
        return existing
    now = now or timezone.now()
    try:
        with transaction.atomic():
            txn = LedgerTransaction.objects.create(
                idempotency_key=key,
                kind=kind,
                booking=booking,
                reference=reference,
                memo=memo[:300],
                created_at=now,
            )
            LedgerEntry.objects.bulk_create(
                [
                    LedgerEntry(
                        transaction=txn,
                        line=i,
                        debit_account=accounts[line.debit],
                        credit_account=accounts[line.credit],
                        amount_paise=line.amount,
                        reference=reference,
                        booking=booking,
                        idempotency_key=f"{key}#{i}",
                        created_at=now,
                    )
                    for i, line in enumerate(lines, start=1)
                ]
            )
    except IntegrityError:
        # Someone posted the same key a moment ago: theirs stands, if it's the same.
        existing = LedgerTransaction.objects.get(idempotency_key=key)
        _same_or_fail(existing, kind, lines)
        return existing
    return txn


def _same_or_fail(existing: LedgerTransaction, kind: str, lines: list[Line]) -> None:
    posted = [
        (e.debit_account.code, e.credit_account.code, e.amount_paise)
        for e in existing.entries.select_related("debit_account", "credit_account").order_by("line")
    ]
    wanted = [(line.debit, line.credit, line.amount) for line in lines]
    if existing.kind != kind or posted != wanted:
        raise LedgerError(
            f"The key {existing.idempotency_key!r} was used for a different movement."
        )


# ---------- Reading ----------


def balance(code: str, *, booking=None, until=None) -> int:
    """The account's balance in its natural sign: debits minus credits for assets and
    expenses, credits minus debits for liabilities, revenue and equity."""
    account = Account.objects.get(code=code)
    entries = LedgerEntry.objects.all()
    if booking is not None:
        entries = entries.filter(booking=booking)
    if until is not None:
        entries = entries.filter(created_at__lt=until)
    debits = entries.filter(debit_account=account).aggregate(s=Sum("amount_paise"))["s"] or 0
    credits = entries.filter(credit_account=account).aggregate(s=Sum("amount_paise"))["s"] or 0
    natural_debit = account.kind in (AccountKind.ASSET, AccountKind.EXPENSE)
    return debits - credits if natural_debit else credits - debits


def trial_balance() -> dict[str, int]:
    """Every account's balance. Assets + expenses always equal the rest."""
    return {code: balance(code) for code in Account.objects.values_list("code", flat=True)}


def is_balanced() -> bool:
    totals = trial_balance()
    kinds = dict(Account.objects.values_list("code", "kind"))
    left = sum(v for c, v in totals.items() if kinds[c] in (AccountKind.ASSET, AccountKind.EXPENSE))
    right = sum(
        v for c, v in totals.items() if kinds[c] not in (AccountKind.ASSET, AccountKind.EXPENSE)
    )
    return left == right
