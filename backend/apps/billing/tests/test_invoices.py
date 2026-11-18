"""GST arithmetic, sequential numbering and issuing invoices."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core import mail

from apps.billing import invoices
from apps.billing.invoices import financial_year, state_of, tax_breakup
from apps.billing.models import Invoice, Subscription
from apps.billing.tests.helpers import plans_on_sale, vendor
from apps.common.models import AuditLog
from apps.media.storage import get_storage

IST = ZoneInfo("Asia/Kolkata")
R18 = Decimal("18")


class TestTaxBreakup:
    def test_within_the_state_splits_cgst_and_sgst(self):
        t = tax_breakup(294882, rate_percent=R18, intra_state=True)  # ₹2,948.82
        assert (t.taxable, t.cgst, t.sgst, t.igst) == (249900, 22491, 22491, 0)
        assert t.taxable + t.cgst + t.sgst == t.total

    def test_across_states_is_igst(self):
        t = tax_breakup(117882, rate_percent=R18, intra_state=False)
        assert (t.taxable, t.cgst, t.sgst, t.igst) == (99900, 0, 0, 17982)

    @pytest.mark.parametrize("total", [1, 99, 101, 117883, 1_000_001])
    def test_the_parts_always_add_up_to_the_paisa(self, total):
        for intra in (True, False):
            t = tax_breakup(total, rate_percent=R18, intra_state=intra)
            assert t.taxable + t.cgst + t.sgst + t.igst == total
            assert abs(t.cgst - t.sgst) <= 1

    def test_negative_charges_are_refused(self):
        with pytest.raises(ValueError):
            tax_breakup(-1, rate_percent=R18, intra_state=True)


def test_financial_years_run_april_to_march():
    assert financial_year(date(2026, 4, 1)) == "2026-27"
    assert financial_year(date(2027, 3, 31)) == "2026-27"
    assert financial_year(date(2027, 4, 1)) == "2027-28"


def test_the_state_comes_from_the_gstin():
    assert state_of("29ABCDE1234F1Z5") == "Karnataka"
    assert state_of("27ABCDE1234F1Z5") == "Maharashtra"
    assert state_of("", "Goa") == "Goa"


pytestmark = pytest.mark.django_db


def subscription_for(owner, plan_code="growth"):
    plan = plans_on_sale()[plan_code]
    return Subscription.objects.create(
        vendor=owner, plan=plan, gateway_subscription_id=f"sub_{owner.pk}", status="active"
    )


class TestNumbering:
    def test_sequential_per_financial_year(self):
        march = datetime(2027, 3, 31, 12, tzinfo=IST)
        april = datetime(2027, 4, 1, 12, tzinfo=IST)
        assert invoices.next_number(march) == "BRT/2026-27/000001"
        assert invoices.next_number(march) == "BRT/2026-27/000002"
        assert invoices.next_number(april) == "BRT/2027-28/000001"


class TestIssuing:
    def test_one_invoice_per_payment_with_the_buyer_as_they_were(
        self, django_capture_on_commit_callbacks, settings
    ):
        settings.BILLING_SUPPLIER = {**settings.BILLING_SUPPLIER, "state": "Karnataka"}
        owner = vendor(
            business_name="Pine Trail Hostel", gstin="29ABCDE1234F1Z5", address="Old Manali Road"
        )
        owner.email = "owner@pinetrail.test"
        owner.save(update_fields=["email"])
        subscription = subscription_for(owner)
        with django_capture_on_commit_callbacks(execute=True):
            invoice = invoices.issue(subscription, payment_id="pay_1", amount_paise=294882)
        again = invoices.issue(subscription, payment_id="pay_1", amount_paise=294882)
        assert again.pk == invoice.pk
        assert Invoice.objects.count() == 1

        invoice.refresh_from_db()
        assert invoice.number.startswith("BRT/") and invoice.number.endswith("/000001")
        assert (invoice.buyer_name, invoice.buyer_gstin, invoice.buyer_state) == (
            "Pine Trail Hostel",
            "29ABCDE1234F1Z5",
            "Karnataka",
        )
        assert (invoice.cgst_paise, invoice.sgst_paise, invoice.igst_paise) == (22491, 22491, 0)
        assert invoice.place_of_supply == "Karnataka"
        assert invoice.sac_code == "998314"
        # The PDF, stored...
        assert invoice.pdf_key == f"invoices/{owner.pk}/{invoice.number.replace('/', '-')}.pdf"
        assert get_storage().read(invoice.pdf_key).startswith(b"%PDF")
        assert len(invoice.pdf_sha256) == 64
        # ...and emailed.
        sent = mail.outbox[-1]
        assert sent.to == ["owner@pinetrail.test"]
        assert invoice.number in sent.subject
        assert sent.attachments[0][2] == "application/pdf"
        assert invoice.emailed_at is not None
        assert AuditLog.objects.filter(action="billing.invoice_issued").count() == 1

    def test_the_pdf_has_the_tax_breakup(self, settings):
        from apps.agreements.pdf import _build

        settings.BILLING_SUPPLIER = {
            **settings.BILLING_SUPPLIER,
            "state": "Karnataka",
            "gstin": "29AAACB1234C1Z9",
        }
        owner = vendor(gstin="27ABCDE1234F1Z5")  # Maharashtra: IGST
        invoice = invoices.issue(subscription_for(owner), payment_id="pay_2", amount_paise=117882)
        html = invoices.render_html(invoice)
        assert "Tax invoice" in html and invoice.number in html
        assert "IGST @ 18%" in html and "₹179.82" in html and "₹1,178.82" in html
        assert "29AAACB1234C1Z9" in html and "27ABCDE1234F1Z5" in html
        assert "CGST" not in html
        _build.cache_clear()

    def test_unfinished_invoices_are_retried_by_the_job(self):
        from apps.agreements.pdf import get_renderer

        owner = vendor()
        owner.email = "o@test.example"
        owner.save(update_fields=["email"])
        get_renderer().fail = True
        invoice = invoices.issue(subscription_for(owner), payment_id="pay_3", amount_paise=117882)
        invoices.finish(invoice.pk)
        invoice.refresh_from_db()
        assert invoice.pdf_key == "" and invoice.emailed_at is None
        get_renderer().fail = False
        assert invoices.finish_pending() == {"invoices": 1}
        invoice.refresh_from_db()
        assert invoice.pdf_key and invoice.emailed_at
