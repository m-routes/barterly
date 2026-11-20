"""A talent's money, for the wallet screen, statements and TDS records.

- pending: stipends held in escrow for their bookings, not yet released (gross, and an
  estimate of what they'd receive after commission, GST and TDS);
- available: released to them and owed, not yet with the payout provider;
- in transit: with the payout provider;
- paid out: payouts the provider has completed.

Statements and TDS records cover one Indian financial year (April to March, India
time), as CSV or PDF.

CA REVIEW NEEDED: the TDS record is a summary for the talent's own records. The
certificate itself is Form 16A, downloaded from TRACES after the TDS return is filed.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone

from apps.money.escrow import PAID_STATES, split
from apps.money.models import (
    Escrow,
    EscrowStatus,
    Payout,
    PayoutAccount,
    PayoutAttemptStatus,
    PayoutStatus,
)

IST = ZoneInfo("Asia/Kolkata")
FY = re.compile(r"^(\d{4})-(\d{2})$")
IN_TRANSIT = (PayoutStatus.SENDING, PayoutStatus.SENT)


class WalletError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------- Financial years ----------


def financial_year(day: date) -> str:
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def fy_bounds(label: str) -> tuple[datetime, datetime]:
    """'2026-27' → [1 Apr 2026 00:00 IST, 1 Apr 2027 00:00 IST)."""
    match = FY.match(label or "")
    if not match or int(match[2]) != (int(match[1]) + 1) % 100:
        raise WalletError("A financial year looks like 2026-27.")
    start = int(match[1])
    return (
        datetime.combine(date(start, 4, 1), time.min, tzinfo=IST),
        datetime.combine(date(start + 1, 4, 1), time.min, tzinfo=IST),
    )


def quarter(moment: datetime) -> str:
    month = moment.astimezone(IST).month
    return {4: "Q1", 5: "Q1", 6: "Q1", 7: "Q2", 8: "Q2", 9: "Q2", 10: "Q3", 11: "Q3", 12: "Q3"}.get(
        month, "Q4"
    )


def rupees(paise: int) -> str:
    return f"{Decimal(paise) / 100:.2f}"


# ---------- The wallet ----------


def _escrows(talent):
    return Escrow.objects.filter(booking__talent=talent).select_related("booking__gig")


def summary(talent, now=None) -> dict:
    from apps.money.payouts import HOLD_MESSAGES, hold_reason

    now = now or timezone.now()
    account = PayoutAccount.objects.filter(talent=talent).first()
    pan = bool(account and account.pan_on_file)
    held = [e for e in _escrows(talent).filter(status=EscrowStatus.HELD) if e.unreleased_paise]
    owed = _escrows(talent).filter(status__in=PAID_STATES)
    available = owed.exclude(payout_status__in=(*IN_TRANSIT, PayoutStatus.SETTLED))
    in_transit = owed.filter(payout_status__in=IN_TRANSIT)
    paid = Payout.objects.filter(talent=talent, status=PayoutAttemptStatus.PROCESSED)
    start, end = fy_bounds(financial_year(now.astimezone(IST).date()))
    tds = _escrows(talent).filter(released_at__gte=start, released_at__lt=end)
    reason = hold_reason(talent.pk, account, now)
    available_paise = available.aggregate(s=Sum("payout_paise"))["s"] or 0
    return {
        "pending_paise": sum(e.unreleased_paise for e in held),
        "pending_net_estimate_paise": sum(
            split(e.unreleased_paise, pan_on_file=pan)["payout"] for e in held
        ),
        "available_paise": available_paise,
        "in_transit_paise": in_transit.aggregate(s=Sum("payout_paise"))["s"] or 0,
        "paid_out_paise": paid.aggregate(s=Sum("amount_paise"))["s"] or 0,
        "tds_this_year_paise": tds.aggregate(s=Sum("tds_paise"))["s"] or 0,
        "financial_year": financial_year(now.astimezone(IST).date()),
        "payout_account": account if account and account.method else None,
        "on_hold_reason": reason[1] if reason else "",
        "on_hold_message": HOLD_MESSAGES[reason[1]] if reason else "",
        "can_request_payout": available_paise > 0 and reason is None,
    }


@dataclass
class Entry:
    kind: str  # "release" or "payout"
    at: datetime
    amount_paise: int
    status: str
    booking_id: str
    gig_title: str
    gross_paise: int = 0
    commission_paise: int = 0
    commission_gst_paise: int = 0
    tds_paise: int = 0
    account: str = ""
    reference: str = ""
    failure_reason: str = ""


def history(
    talent,
    *,
    kind: str = "",
    status: str = "",
    start: date | None = None,
    end: date | None = None,
    fy: str = "",
) -> list[Entry]:
    """Releases and payout attempts, newest first, filtered."""
    entries: list[Entry] = []
    if kind in ("", "release"):
        for e in _escrows(talent).filter(released_at__isnull=False):
            entries.append(
                Entry(
                    "release",
                    e.released_at,
                    e.payout_paise,
                    e.payout_status or "owed",
                    str(e.booking_id),
                    e.booking.gig.title,
                    e.released_paise,
                    e.commission_paise,
                    e.commission_gst_paise,
                    e.tds_paise,
                )
            )
    if kind in ("", "payout"):
        for p in Payout.objects.filter(talent=talent).select_related("escrow__booking__gig"):
            entries.append(
                Entry(
                    "payout",
                    p.processed_at or p.created_at,
                    p.amount_paise,
                    p.status,
                    str(p.escrow.booking_id),
                    p.escrow.booking.gig.title,
                    account=p.account_display,
                    reference=p.utr or p.provider_payout_id,
                    failure_reason=p.failure_reason,
                )
            )
    if fy:
        lo, hi = fy_bounds(fy)
        entries = [x for x in entries if lo <= x.at < hi]
    if start:
        entries = [x for x in entries if x.at.astimezone(IST).date() >= start]
    if end:
        entries = [x for x in entries if x.at.astimezone(IST).date() <= end]
    if status:
        entries = [x for x in entries if x.status == status]
    return sorted(entries, key=lambda x: x.at, reverse=True)


# ---------- Statements and TDS ----------


def statement(talent, fy: str) -> dict:
    lo, hi = fy_bounds(fy)
    rows = []
    for e in (
        _escrows(talent).filter(released_at__gte=lo, released_at__lt=hi).order_by("released_at")
    ):
        paid = e.payouts.filter(status=PayoutAttemptStatus.PROCESSED).first()
        rows.append(
            {
                "date": e.released_at.astimezone(IST).date(),
                "booking_id": str(e.booking_id),
                "gig_title": e.booking.gig.title,
                "gross_paise": e.released_paise,
                "commission_paise": e.commission_paise,
                "commission_gst_paise": e.commission_gst_paise,
                "tds_paise": e.tds_paise,
                "net_paise": e.payout_paise,
                "payout_status": e.payout_status or "owed",
                "paid_on": paid.processed_at.astimezone(IST).date()
                if paid and paid.processed_at
                else None,
                "utr": paid.utr if paid else "",
            }
        )
    totals = {
        k: sum(r[k] for r in rows)
        for k in (
            "gross_paise",
            "commission_paise",
            "commission_gst_paise",
            "tds_paise",
            "net_paise",
        )
    }
    return {"financial_year": fy, "talent": _party(talent), "rows": rows, "totals": totals}


def tds_record(talent, fy: str) -> dict:
    lo, hi = fy_bounds(fy)
    account = PayoutAccount.objects.filter(talent=talent).first()
    releases = _escrows(talent).filter(released_at__gte=lo, released_at__lt=hi, tds_paise__gt=0)
    quarters = {
        q: {"quarter": q, "amount_credited_paise": 0, "tds_paise": 0}
        for q in ("Q1", "Q2", "Q3", "Q4")
    }
    rows = []
    for e in releases.order_by("released_at"):
        q = quarter(e.released_at)
        quarters[q]["amount_credited_paise"] += e.released_paise
        quarters[q]["tds_paise"] += e.tds_paise
        rows.append(
            {
                "date": e.released_at.astimezone(IST).date(),
                "quarter": q,
                "booking_id": str(e.booking_id),
                "gig_title": e.booking.gig.title,
                "amount_credited_paise": e.released_paise,
                "tds_paise": e.tds_paise,
            }
        )
    return {
        "financial_year": fy,
        "section": settings.ESCROW_TDS_SECTION,
        "deductor": {
            "name": settings.BILLING_SUPPLIER["legal_name"],
            "address": settings.BILLING_SUPPLIER["address"],
            "tan": settings.ESCROW_TDS_TAN,
        },
        "deductee": {**_party(talent), "pan_on_file": bool(account and account.pan_on_file)},
        "quarters": list(quarters.values()),
        "rows": rows,
        "total_credited_paise": sum(q["amount_credited_paise"] for q in quarters.values()),
        "total_tds_paise": sum(q["tds_paise"] for q in quarters.values()),
        "note": "A summary for your records. Your TDS certificate is Form 16A, issued "
        "after each quarter's TDS return; the credit shows in your Form 26AS.",
    }


def _party(talent) -> dict:
    profile = getattr(talent, "talent_profile", None)
    return {"name": getattr(profile, "display_name", "") or str(talent.phone), "id": str(talent.pk)}


STATEMENT_COLUMNS = [
    ("date", "Date"),
    ("booking_id", "Booking"),
    ("gig_title", "Gig"),
    ("gross_paise", "Gross (INR)"),
    ("commission_paise", "Commission (INR)"),
    ("commission_gst_paise", "GST on commission (INR)"),
    ("tds_paise", "TDS (INR)"),
    ("net_paise", "Net (INR)"),
    ("payout_status", "Payout"),
    ("paid_on", "Paid on"),
    ("utr", "Bank reference"),
]
TDS_COLUMNS = [
    ("date", "Date"),
    ("quarter", "Quarter"),
    ("booking_id", "Booking"),
    ("gig_title", "Gig"),
    ("amount_credited_paise", "Amount credited (INR)"),
    ("tds_paise", "TDS deducted (INR)"),
]


def to_csv(rows: list[dict], columns) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_cell(key, row[key]) for key, _ in columns])
    return out.getvalue().encode("utf-8-sig")  # a BOM so Excel reads ₹ and Hindi right


def _cell(key: str, value) -> str:
    if key.endswith("_paise"):
        return rupees(value)
    text = "" if value is None else str(value)
    # Spreadsheet formula injection: a gig title starting with = runs as a formula.
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def to_pdf(template: str, context: dict) -> bytes:
    from apps.agreements.pdf import get_renderer

    html = render_to_string(f"money/{template}.html", context)
    return get_renderer().render(html)
