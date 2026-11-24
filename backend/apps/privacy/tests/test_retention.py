from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import TalentFactory
from apps.bookings import jobs
from apps.common.models import AuditLog
from apps.money.models import GatewayEvent
from apps.notifications.models import Notification, PushDevice
from apps.privacy.services import retention

pytestmark = pytest.mark.django_db


def test_old_data_is_purged_and_each_purge_is_audited(settings):
    user = TalentFactory()
    now = timezone.now()
    old = now - timedelta(days=400)
    Notification.objects.create(
        user=user, kind="x", title="Old", body="", status="sent", created_at=old
    )
    Notification.objects.create(user=user, kind="x", title="New", body="", status="sent")
    PushDevice.objects.create(user=user, token="old", platform="android", last_seen_at=old)
    PushDevice.objects.create(user=user, token="new", platform="android")
    GatewayEvent.objects.create(
        event_id="evt_1",
        event="payment.captured",
        payload={"contact": "+919876500000"},
        received_at=old,
    )

    result = retention.purge(now)

    assert result["notifications"] == 1 and result["push_devices"] == 1
    assert result["gateway_payloads"] == 1
    assert list(Notification.objects.values_list("title", flat=True)) == ["New"]
    assert list(PushDevice.objects.values_list("token", flat=True)) == ["new"]
    event = GatewayEvent.objects.get()
    assert event.payload == {} and event.event_id == "evt_1"  # the record stays
    purges = {
        e.object_id: e.after for e in AuditLog.objects.filter(action="privacy.retention_purge")
    }
    assert purges["notifications"]["count"] == 1
    assert purges["notifications"]["days"] == settings.PRIVACY_RETENTION_DAYS["notifications"]
    assert "push_devices" in purges and "gateway_payloads" in purges
    assert "job_runs" not in purges  # nothing purged, nothing logged

    assert retention.purge(now)["notifications"] == 0  # idempotent


def test_queued_notifications_are_never_purged():
    user = TalentFactory()
    Notification.objects.create(
        user=user,
        kind="x",
        title="Waiting",
        body="",
        status="queued",
        created_at=timezone.now() - timedelta(days=999),
    )
    retention.purge(timezone.now())
    assert Notification.objects.exists()


def test_every_kind_has_a_retention_setting(settings):
    assert set(retention.PURGES) == set(settings.PRIVACY_RETENTION_DAYS)


def test_the_jobs_are_scheduled():
    assert "privacy_retention" in jobs.JOBS and "privacy_deletions" in jobs.JOBS
    run = jobs.run("privacy_retention", trigger="test")
    assert run.error == "" and "data_exports" in run.result
