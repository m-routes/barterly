"""The wallet, history, statements and TDS records, and their API."""

import csv
import io
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory
from apps.backoffice.roles import AdminRole, sync_roles
from apps.money import deliverables, payouts, wallet
from apps.money.gateway.fake import FakePayoutProvider
from apps.money.models import Escrow, PayoutRun
from apps.money.tests.helpers import (
    STIPEND,
    check_in,
    funded,
    payout_account,
    send_payout,
)
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
IST = ZoneInfo("Asia/Kolkata")
PAYOUT = 447_800  # ₹5,000 less 8% commission, 18% GST on it, 1% TDS
TDS = 5_000


def released(talent=None):
    booking, record = funded()
    if not hasattr(booking.talent, "payout_account"):
        payout_account(booking.talent)
    check_in(booking)
    submission = deliverables.submit(booking.pk, talent=booking.talent, note="Reels")
    deliverables.review(submission.pk, vendor=booking.vendor, approve=True)
    record.refresh_from_db()
    return booking, record


def at(day: date) -> datetime:
    return datetime.combine(day, time(12), tzinfo=IST)


class TestFinancialYears:
    def test_bounds_and_labels(self):
        assert wallet.financial_year(date(2027, 3, 31)) == "2026-27"
        assert wallet.financial_year(date(2027, 4, 1)) == "2027-28"
        lo, hi = wallet.fy_bounds("2026-27")
        assert (lo, hi) == (
            at(date(2026, 4, 1)).replace(hour=0),
            at(date(2027, 4, 1)).replace(hour=0),
        )
        for bad in ("2026", "2026-28", "26-27", ""):
            with pytest.raises(wallet.WalletError):
                wallet.fy_bounds(bad)
        assert wallet.quarter(at(date(2026, 4, 1))) == "Q1"
        assert wallet.quarter(at(date(2027, 1, 15))) == "Q4"


class TestWallet:
    def test_pending_available_and_paid(self):
        booking, record = funded()
        payout_account(booking.talent)
        empty = wallet.summary(booking.talent)
        assert empty["pending_paise"] == STIPEND
        assert empty["pending_net_estimate_paise"] == PAYOUT
        assert empty["available_paise"] == 0
        check_in(booking)
        submission = deliverables.submit(booking.pk, talent=booking.talent, note="Reels")
        deliverables.review(submission.pk, vendor=booking.vendor, approve=True)
        owed = wallet.summary(booking.talent)
        assert (owed["pending_paise"], owed["available_paise"]) == (0, PAYOUT)
        assert owed["can_request_payout"] and owed["tds_this_year_paise"] == TDS
        payout = send_payout(record.pk).payouts.get()
        sent = wallet.summary(booking.talent)
        assert (sent["available_paise"], sent["in_transit_paise"]) == (0, PAYOUT)
        payouts.accept(payout.pk, provider_id=payout.provider_payout_id, processed=True)
        done = wallet.summary(booking.talent)
        assert (done["in_transit_paise"], done["paid_out_paise"]) == (0, PAYOUT)

    def test_a_hold_is_explained(self):
        booking, _ = released()
        account = booking.talent.payout_account
        account.hold_until = timezone.now() + timezone.timedelta(hours=5)
        account.save()
        summary = wallet.summary(booking.talent)
        assert summary["on_hold_reason"] == "account_recently_changed"
        assert "24 hours" in summary["on_hold_message"] and not summary["can_request_payout"]

    def test_history_filters(self):
        booking, record = released()
        send_payout(record.pk)
        both = wallet.history(booking.talent)
        assert [e.kind for e in both] == ["payout", "release"]
        assert [e.kind for e in wallet.history(booking.talent, kind="release")] == ["release"]
        assert wallet.history(booking.talent, status="processing")[0].kind == "payout"
        fy = wallet.financial_year(timezone.localdate())
        assert len(wallet.history(booking.talent, fy=fy)) == 2
        assert wallet.history(booking.talent, fy="2001-02") == []
        tomorrow = timezone.localdate() + timezone.timedelta(days=60)
        assert wallet.history(booking.talent, start=tomorrow) == []
        assert wallet.history(TalentFactory()) == []


class TestStatements:
    def released_in(self, day):
        booking, record = released()
        Escrow.objects.filter(pk=record.pk).update(released_at=at(day))
        return booking, record

    def test_a_statement_covers_one_financial_year(self):
        booking, _ = self.released_in(date(2026, 6, 10))
        data = wallet.statement(booking.talent, "2026-27")
        assert len(data["rows"]) == 1
        row = data["rows"][0]
        assert (row["gross_paise"], row["tds_paise"], row["net_paise"]) == (STIPEND, TDS, PAYOUT)
        assert data["totals"]["net_paise"] == PAYOUT
        assert wallet.statement(booking.talent, "2025-26")["rows"] == []

    def test_tds_is_summed_by_quarter(self):
        booking, _ = self.released_in(date(2026, 11, 1))
        record = wallet.tds_record(booking.talent, "2026-27")
        by_quarter = {q["quarter"]: q["tds_paise"] for q in record["quarters"]}
        assert by_quarter == {"Q1": 0, "Q2": 0, "Q3": TDS, "Q4": 0}
        assert record["total_tds_paise"] == TDS and record["section"] == "194-O"
        assert record["deductee"]["pan_on_file"] is True
        assert "Form 16A" in record["note"]

    def test_csv_is_in_rupees_and_safe_for_spreadsheets(self):
        rows = [
            {
                "date": date(2026, 6, 10),
                "booking_id": "b",
                "gig_title": "=HYPERLINK(1)",
                "gross_paise": 500_000,
                "commission_paise": 40_000,
                "commission_gst_paise": 7_200,
                "tds_paise": 5_000,
                "net_paise": 447_800,
                "payout_status": "settled",
                "paid_on": None,
                "utr": "",
            }
        ]
        text = wallet.to_csv(rows, wallet.STATEMENT_COLUMNS).decode("utf-8-sig")
        parsed = list(csv.reader(io.StringIO(text)))
        assert parsed[0][0] == "Date" and parsed[1][2] == "'=HYPERLINK(1)"
        assert parsed[1][3] == "5000.00" and parsed[1][7] == "4478.00"

    def test_pdfs_render(self):
        booking, _ = self.released_in(date(2026, 6, 10))
        assert wallet.to_pdf("statement", wallet.statement(booking.talent, "2026-27"))
        assert wallet.to_pdf("tds", wallet.tds_record(booking.talent, "2026-27"))


class TestApi:
    def test_linking_an_account(self):
        talent = TalentFactory()
        url = reverse("money:payout-account")
        assert client_for(talent).get(url).status_code == 404
        bad = client_for(talent).put(url, {"method": "upi", "vpa": "nope"}, format="json")
        assert bad.status_code == 400
        response = client_for(talent).put(
            url,
            {
                "method": "bank",
                "account_number": "123456789012",
                "ifsc": "HDFC0001234",
                "holder_name": "Asha Rao",
            },
            format="json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["display"] == "HDFC0001234 ••••9012" and "account_number" not in body
        assert client_for(talent).get(url).json()["validation_status"] == "pending"
        vendor_try = client_for(AdminUserFactory()).get(url)
        assert vendor_try.status_code == 403

    def test_wallet_history_and_payout(self):
        booking, _ = released()
        client = client_for(booking.talent)
        assert client.get(reverse("money:wallet")).json()["available_paise"] == PAYOUT
        history = client.get(reverse("money:wallet-history"), {"kind": "release"}).json()
        assert history["count"] == 1 and history["results"][0]["amount_paise"] == PAYOUT
        assert client.get(reverse("money:wallet-history"), {"fy": "2026"}).status_code == 400
        run = client.post(reverse("money:wallet-payout")).json()
        assert run["sent"] == 1
        assert client.post(reverse("money:wallet-payout")).status_code == 429

    def test_statement_and_tds_downloads(self):
        booking, record = released()
        Escrow.objects.filter(pk=record.pk).update(released_at=at(date(2026, 6, 10)))
        client = client_for(booking.talent)
        assert (
            client.get(reverse("money:statement", args=["2026-27"])).json()["totals"]["net_paise"]
            == PAYOUT
        )
        csv_file = client.get(reverse("money:statement-file", args=["2026-27", "csv"]))
        assert csv_file["Content-Type"].startswith("text/csv")
        assert 'filename="barterly-statement-2026-27.csv"' in csv_file["Content-Disposition"]
        pdf = client.get(reverse("money:tds-file", args=["2026-27", "pdf"]))
        assert pdf["Content-Type"] == "application/pdf" and pdf.content
        assert client.get(reverse("money:tds", args=["2026-27"])).json()["total_tds_paise"] == TDS
        assert client.get(reverse("money:tds-file", args=["2026-27", "xls"])).status_code == 404
        assert client.get(reverse("money:statement", args=["2026"])).status_code == 400

    def test_admin_payout_runs(self):
        sync_roles()
        finance = AdminUserFactory()
        finance.groups.add(Group.objects.get(name=AdminRole.FINANCE))
        released()
        url = reverse("money:payout-runs")
        assert client_for(AdminUserFactory()).post(url).status_code == 403
        started = client_for(finance).post(url)
        assert started.status_code == 201 and started.json()["sent"] == 1
        run_id = started.json()["id"]
        detail = client_for(finance).get(reverse("money:payout-run", args=[run_id])).json()
        assert detail["payouts"][0]["account_display"] == "ta•••@okicici"
        assert client_for(finance).get(url).json()["count"] == 1
        assert PayoutRun.objects.get().started_by == finance

    def test_admin_retry_and_failed_queue(self, settings):
        sync_roles()
        finance = AdminUserFactory()
        finance.groups.add(Group.objects.get(name=AdminRole.FINANCE))
        _, record = released()
        from apps.money.gateway.base import GatewayError

        FakePayoutProvider.fail_next.append(GatewayError("down"))
        failed = send_payout(record.pk).payouts.get()
        listed = client_for(finance).get(reverse("money:payouts"), {"status": "failed"}).json()
        assert [p["id"] for p in listed["results"]] == [str(failed.pk)]
        url = reverse("money:payout-retry", args=[failed.pk])
        assert client_for(finance).post(url, {}, format="json").status_code == 400
        retried = client_for(finance).post(url, {"note": "Bank is back"}, format="json")
        assert retried.status_code == 200 and retried.json()["sent"] == 1

    def test_the_payout_webhook_endpoint(self, client, settings):
        from apps.money.gateway.fake import signed_x

        url = reverse("money:payout-webhook")
        body, headers = signed_x({"event": "payout.queued"}, "wrong", "e1")
        assert (
            client.post(url, body, content_type="application/json", headers=headers).status_code
            == 400
        )
        body, headers = signed_x(
            {"event": "payout.queued"}, settings.RAZORPAYX_WEBHOOK_SECRET, "e2"
        )
        good = client.post(url, body, content_type="application/json", headers=headers)
        assert good.status_code == 200 and good.json() == {"outcome": "not a Barterly payout"}
