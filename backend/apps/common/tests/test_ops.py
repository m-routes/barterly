"""Ops events are an interface with monitoring.tf: pin the names and where they fire."""

import logging
import re
from pathlib import Path

import pytest

from apps.common import backlog
from apps.common.ops import EVENTS, ops_event

MONITORING_TF = (
    Path(__file__).resolve().parents[4] / "infra/terraform/modules/environment/monitoring.tf"
)


def events_in(caplog) -> list[dict]:
    return [vars(r) for r in caplog.records if getattr(r, "ops_event", None)]


def test_every_event_has_a_metric_in_terraform():
    terraform = MONITORING_TF.read_text()
    # A key of ops_counters (`name = {`) or a literal filter on it (`\"name\"`).
    missing = {
        name for name in EVENTS if not re.search(rf'\b{name}\s*=\s*{{|\\"{name}\\"', terraform)
    }
    assert not missing, f"monitoring.tf has no metric for {missing}"


def test_unknown_events_are_refused():
    with pytest.raises(ValueError):
        ops_event("made_up")


def test_event_carries_its_name_and_fields(caplog):
    caplog.set_level(logging.INFO, logger="barterly.ops")
    ops_event("job_failed", job="payout_run", error="Boom")
    [event] = events_in(caplog)
    assert event["ops_event"] == "job_failed"
    assert event["job"] == "payout_run"


@pytest.mark.django_db
def test_failed_job_emits_job_failed(caplog, monkeypatch):
    from apps.bookings import jobs

    def boom(now):
        raise RuntimeError("nope")

    monkeypatch.setitem(jobs.JOBS, "expire_offers", boom)
    caplog.set_level(logging.INFO, logger="barterly.ops")
    with pytest.raises(RuntimeError):
        jobs.run("expire_offers")
    assert [e["job"] for e in events_in(caplog)] == ["expire_offers"]


@pytest.mark.django_db
def test_bad_webhook_signature_emits_webhook_rejected(caplog, client):
    caplog.set_level(logging.INFO, logger="barterly.ops")
    response = client.post(
        "/api/v1/money/webhooks/razorpay/",
        data=b'{"event": "payment.captured"}',
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE="bad",
        HTTP_X_RAZORPAY_EVENT_ID="evt_1",
    )
    assert response.status_code == 400
    [event] = events_in(caplog)
    assert (event["ops_event"], event["provider"]) == ("webhook_rejected", "razorpay")


@pytest.mark.django_db
def test_backlog_counts_stuck_work(caplog):
    from datetime import timedelta

    from django.utils import timezone

    from apps.bookings.models import JobRun

    now = timezone.now()
    JobRun.objects.create(job="payout_run", started_at=now - timedelta(hours=1), error="X")
    JobRun.objects.create(job="payout_run", started_at=now - timedelta(days=2), error="old")
    caplog.set_level(logging.INFO, logger="barterly.ops")
    result = backlog.report(now)
    assert result == {
        "notifications_stuck": 0,
        "notifications_dead_24h": 0,
        "payouts_stuck": 0,
        "jobs_failed_24h": 1,
        "support_overdue": 0,
        "safety_reviews_overdue": 0,
    }
    [event] = events_in(caplog)
    assert event["jobs_failed_24h"] == 1


def test_reconciliation_and_dead_letters_are_wired():
    root = Path(__file__).resolve().parents[2]
    assert (
        'ops_event(\n            "reconciliation_mismatch"'
        in (root / "money/reconciliation.py").read_text()
    )
    assert '"notification_dead_letter"' in (root / "notifications/services.py").read_text()
    assert '"db_connection_failed"' in (root.parent / "apps/core/services/db_retry.py").read_text()
