"""The daily reconciliation: the ledger's totals for one India day against the
gateway's report for it (payments captured, refunds, transfers, fees). Any difference,
or a ledger out of balance, raises an alert. Re-running a day replaces its result.

A transfer that fails on a later day than it was made is reversed in the ledger on the
day of the failure, so it shows as a difference on both days: check those by hand.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone

from apps.money import alerts, ledger
from apps.money.gateway.base import GatewayError, get_gateway
from apps.money.ledger import GATEWAY
from apps.money.models import LedgerEntry, ReconciliationRun

IST = ZoneInfo("Asia/Kolkata")
FIELDS = ("captured", "refunded", "transferred", "fees")


def _sum(entries) -> int:
    return entries.aggregate(s=Sum("amount_paise"))["s"] or 0


def ledger_totals(day: date) -> dict[str, int]:
    start = datetime.combine(day, time.min, tzinfo=IST)
    entries = LedgerEntry.objects.filter(
        created_at__gte=start, created_at__lt=start + timedelta(days=1)
    )

    def kind(name):
        return entries.filter(transaction__kind=name)

    return {
        "captured": _sum(kind("escrow_funded").filter(debit_account__code=GATEWAY)),
        "fees": _sum(kind("escrow_funded").filter(credit_account__code=GATEWAY)),
        "refunded": _sum(kind("refund_processed")),
        "transferred": _sum(kind("payout_sent")) - _sum(kind("payout_reversed")),
    }


def run(day: date | None = None, now=None) -> ReconciliationRun:
    now = now or timezone.now()
    day = day or (now.astimezone(IST).date() - timedelta(days=1))
    ours = ledger_totals(day)
    mismatches: list[dict] = []
    try:
        report = get_gateway().day_totals(day)
        theirs = {f: getattr(report, f) for f in FIELDS}
    except GatewayError as exc:
        theirs = {}
        mismatches.append({"field": "gateway", "error": str(exc)})
    for field in FIELDS if theirs else ():
        if ours[field] != theirs[field]:
            mismatches.append(
                {
                    "field": field,
                    "ledger": ours[field],
                    "gateway": theirs[field],
                    "difference": ours[field] - theirs[field],
                }
            )
    if not ledger.is_balanced():
        mismatches.append({"field": "trial_balance", "error": "The ledger doesn't balance."})
    result, _ = ReconciliationRun.objects.update_or_create(
        day=day,
        defaults={
            "ledger": ours,
            "gateway": theirs,
            "mismatches": mismatches,
            "ok": not mismatches,
            "created_at": now,
        },
    )
    if mismatches:
        alerts.raise_alert(
            f"Reconciliation mismatch for {day}",
            {"day": str(day), "mismatches": mismatches},
            obj=result,
        )
    return result


def run_job(now) -> dict[str, int]:
    result = run(now=now)
    return {"ok": int(result.ok), "mismatches": len(result.mismatches)}
