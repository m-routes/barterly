"""GST tax invoices: one per charge.

- tax_breakup(): the GST arithmetic, pure. The gateway charges a GST-inclusive amount;
  the taxable value is worked back from it at BILLING_GST_RATE (18%, SAC 998314 for
  online software services). Same state as the supplier: CGST + SGST, half each.
  Otherwise IGST. Rounded to the paisa so the parts always add up to the total.
- next_number(): sequential and gap-free per Indian financial year (April to March),
  e.g. BRT/2026-27/000042, allocated under a row lock in the issuing transaction.
- issue(): records the invoice for a payment (once: the payment id is unique), then,
  after the transaction commits, renders the PDF with WeasyPrint, stores it in Cloud
  Storage and emails it to the vendor. The `billing_invoices` job retries anything
  left unrendered or unsent.

The supplier's details (legal name, GSTIN, address, state) are settings
(BILLING_SUPPLIER); the buyer's come from the vendor profile, copied at issue.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.billing.models import Invoice, InvoiceCounter, Subscription
from apps.common.services.audit import log_action
from apps.media.storage import get_storage

logger = logging.getLogger(__name__)
SAC_CODE = "998314"

# GSTIN state codes (the first two digits), for working out the place of supply.
STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}


# ---------- The arithmetic (pure) ----------


@dataclass(frozen=True)
class TaxBreakup:
    taxable: int
    cgst: int
    sgst: int
    igst: int
    total: int
    rate: Decimal
    intra_state: bool


def tax_breakup(total_paise: int, *, rate_percent: Decimal, intra_state: bool) -> TaxBreakup:
    """Split a GST-inclusive total into taxable value and tax, in whole paise."""
    if total_paise < 0:
        raise ValueError("A charge can't be negative.")
    rate = Decimal(rate_percent)
    taxable = int(
        (Decimal(total_paise) * 100 / (100 + rate)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )
    tax = total_paise - taxable
    if intra_state:
        cgst = tax // 2
        return TaxBreakup(taxable, cgst, tax - cgst, 0, total_paise, rate, True)
    return TaxBreakup(taxable, 0, 0, tax, total_paise, rate, False)


def financial_year(day: date) -> str:
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def state_of(gstin: str, fallback: str = "") -> str:
    return STATE_CODES.get((gstin or "")[:2], fallback)


def rupees(paise: int) -> str:
    return f"₹{Decimal(paise) / 100:,.2f}"


# ---------- Numbering ----------


def next_number(issued: datetime) -> str:
    """The next number for the issue date's financial year. Call inside a transaction:
    the counter row stays locked until it commits, so numbers never repeat or skip."""
    year = financial_year(timezone.localdate(issued))
    counter, _ = InvoiceCounter.objects.select_for_update().get_or_create(financial_year=year)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"{settings.BILLING_INVOICE_PREFIX}/{year}/{counter.last:06d}"


# ---------- Issuing ----------


def issue(
    subscription: Subscription,
    *,
    payment_id: str,
    amount_paise: int,
    now=None,
    period_start=None,
    period_end=None,
) -> Invoice:
    """The invoice for one charge; the same payment id returns the one already made."""
    existing = Invoice.objects.filter(gateway_payment_id=payment_id).first()
    if existing:
        return existing
    now = now or timezone.now()
    supplier = dict(settings.BILLING_SUPPLIER)
    profile = getattr(subscription.vendor, "vendor_profile", None)
    buyer_gstin = (getattr(profile, "gstin", "") or "").upper()
    buyer_state = state_of(buyer_gstin, getattr(profile, "state", "") or "")
    intra = bool(buyer_state) and buyer_state == supplier.get("state")
    tax = tax_breakup(
        amount_paise, rate_percent=Decimal(str(settings.BILLING_GST_RATE)), intra_state=intra
    )
    with transaction.atomic():
        invoice = Invoice.objects.create(
            number=next_number(now),
            vendor=subscription.vendor,
            subscription=subscription,
            gateway_payment_id=payment_id,
            plan_name=subscription.plan.name,
            period_start=period_start,
            period_end=period_end,
            taxable_paise=tax.taxable,
            cgst_paise=tax.cgst,
            sgst_paise=tax.sgst,
            igst_paise=tax.igst,
            total_paise=tax.total,
            gst_rate_percent=tax.rate,
            sac_code=SAC_CODE,
            place_of_supply=buyer_state or supplier.get("state", ""),
            supplier=supplier,
            buyer_name=(getattr(profile, "business_name", "") or "") or subscription.vendor.phone,
            buyer_gstin=buyer_gstin,
            buyer_address=getattr(profile, "address", "") or "",
            buyer_state=buyer_state,
            buyer_email=subscription.vendor.email or "",
            issued_at=now,
        )
        log_action(
            actor=None,
            action="billing.invoice_issued",
            obj=invoice,
            after={
                "number": invoice.number,
                "payment_id": payment_id,
                "total_paise": invoice.total_paise,
                "tax_paise": invoice.tax_paise,
            },
        )
        transaction.on_commit(lambda: finish(invoice.pk))
    return invoice


def storage_key(invoice: Invoice) -> str:
    return f"invoices/{invoice.vendor_id}/{invoice.number.replace('/', '-')}.pdf"


def render_html(invoice: Invoice) -> str:
    return render_to_string(
        "billing/invoice.html",
        {
            "invoice": invoice,
            "supplier": invoice.supplier,
            "taxable": rupees(invoice.taxable_paise),
            "cgst": rupees(invoice.cgst_paise),
            "sgst": rupees(invoice.sgst_paise),
            "igst": rupees(invoice.igst_paise),
            "total": rupees(invoice.total_paise),
            "half_rate": invoice.gst_rate_percent / 2,
            "intra_state": invoice.igst_paise == 0 and invoice.tax_paise > 0,
        },
    )


def render(invoice_id) -> Invoice:
    """Draw up and store the PDF (once)."""
    from apps.agreements.pdf import get_renderer

    invoice = Invoice.objects.select_related("vendor").get(pk=invoice_id)
    if invoice.pdf_key:
        return invoice
    data = get_renderer().render(render_html(invoice))
    key = storage_key(invoice)
    get_storage().write(key, data, content_type="application/pdf")
    Invoice.objects.filter(pk=invoice.pk, pdf_key="").update(
        pdf_key=key, pdf_sha256=hashlib.sha256(data).hexdigest()
    )
    invoice.refresh_from_db()
    return invoice


def email(invoice_id, now=None) -> Invoice:
    """Send the PDF to the vendor's email (once)."""
    invoice = Invoice.objects.get(pk=invoice_id)
    if invoice.emailed_at or not invoice.buyer_email or not invoice.pdf_key:
        return invoice
    data = get_storage().read(invoice.pdf_key)
    message = EmailMessage(
        subject=f"Barterly invoice {invoice.number}",
        body=(
            f"Thanks for your payment of {rupees(invoice.total_paise)} for the "
            f"{invoice.plan_name} plan. Your GST invoice {invoice.number} is attached. "
            "You'll also find it under Billing in the Barterly console."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[invoice.buyer_email],
    )
    message.attach(f"{invoice.number.replace('/', '-')}.pdf", data, "application/pdf")
    message.send(fail_silently=False)
    Invoice.objects.filter(pk=invoice.pk).update(emailed_at=now or timezone.now())
    invoice.refresh_from_db()
    return invoice


def finish(invoice_id) -> None:
    """Render, store and email; failures are left for the job to retry."""
    try:
        render(invoice_id)
        email(invoice_id)
    except Exception:
        logger.exception("Invoice not finished; the job will retry", extra={"id": str(invoice_id)})


def finish_pending(now=None) -> dict[str, int]:
    """Job: invoices without a PDF, or not yet emailed."""
    from django.db.models import Q

    pending = Invoice.objects.filter(Q(pdf_key="") | Q(emailed_at__isnull=True, buyer_email__gt=""))
    done = 0
    for pk in list(pending.values_list("pk", flat=True)[:100]):
        finish(pk)
        done += 1
    return {"invoices": done}
