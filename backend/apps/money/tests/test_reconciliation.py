"""The daily reconciliation against the gateway's report."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from apps.bookings import jobs
from apps.common.models import AuditLog
from apps.money import reconciliation
from apps.money.gateway.base import DayTotals, GatewayError
from apps.money.gateway.fake import FakeEscrowGateway
from apps.money.models import ReconciliationRun
from apps.money.tests.helpers import GATEWAY_FEE, TOTAL, funded

pytestmark = pytest.mark.django_db
DAY = date(2026, 11, 18)
NOON = datetime.combine(DAY, time(12), tzinfo=ZoneInfo("Asia/Kolkata"))


def test_matching_totals_are_ok():
    funded(now=NOON)
    FakeEscrowGateway.totals[DAY] = DayTotals(captured=TOTAL, fees=GATEWAY_FEE)
    result = reconciliation.run(DAY)
    assert result.ok and result.mismatches == []
    assert result.ledger == {
        "captured": TOTAL,
        "fees": GATEWAY_FEE,
        "refunded": 0,
        "paid_out": 0,
    }
    assert not AuditLog.objects.filter(action="money.alert").exists()


def test_a_mismatch_raises_an_alert(mailoutbox, settings):
    settings.ESCROW_ALERT_EMAILS = ["money@barterly.test"]
    funded(now=NOON)
    FakeEscrowGateway.totals[DAY] = DayTotals(captured=TOTAL + 100, fees=GATEWAY_FEE)
    result = reconciliation.run(DAY)
    assert not result.ok
    assert result.mismatches == [
        {"field": "captured", "ledger": TOTAL, "gateway": TOTAL + 100, "difference": -100}
    ]
    assert AuditLog.objects.filter(action="money.alert").count() == 1
    assert "Reconciliation mismatch" in mailoutbox[0].subject


def test_other_days_dont_count():
    funded(now=NOON)
    result = reconciliation.run(date(2026, 11, 17))
    assert result.ok and result.ledger["captured"] == 0


def test_a_gateway_error_is_a_mismatch():
    FakeEscrowGateway.fail_next.append(GatewayError("timeout"))
    result = reconciliation.run(DAY)
    assert not result.ok and result.mismatches[0]["field"] == "gateway"


def test_rerunning_a_day_replaces_it():
    reconciliation.run(DAY)
    FakeEscrowGateway.totals[DAY] = DayTotals(refunded=5)
    reconciliation.run(DAY)
    assert ReconciliationRun.objects.get(day=DAY).ok is False


def test_the_job_checks_yesterday():
    run = jobs.run("escrow_reconcile", trigger="manual", now=NOON)
    assert run.result == {"ok": 1, "mismatches": 0}
    assert ReconciliationRun.objects.get().day == date(2026, 11, 17)


def test_the_escrow_jobs_are_registered():
    assert {"escrow_auto_release", "payout_run", "payout_validations", "escrow_reconcile"} <= set(
        jobs.JOBS
    )
