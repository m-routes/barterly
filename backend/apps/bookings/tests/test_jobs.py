from datetime import timedelta
from io import StringIO
from unittest import mock

import psycopg
import pytest
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.constants import ApplicationStatus as A
from apps.applications.models import Application
from apps.applications.services import apply, transition
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings import jobs
from apps.bookings.lifecycle import STALE_INTERVIEW_AFTER, Actor
from apps.bookings.models import JobRun
from apps.bookings.scheduler import GoogleOidcVerifier, SchedulerAuthError
from apps.bookings.tests.fakes import GOOD_TOKEN, OTHER_CALLER_TOKEN
from apps.bookings.tests.helpers import offered
from apps.common.models import AuditLog
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def interviewing(days_ago: int):
    gig = live_gig()
    application = apply(
        eligible_talent(), gig.pk, pitch="Hi", answers=[], attachments=[], **dates()
    )
    transition(application.pk, A.INTERVIEW, actor=Actor.VENDOR, user=gig.vendor)
    Application.objects.filter(pk=application.pk).update(
        status_changed_at=timezone.now() - timedelta(days=days_ago)
    )
    return application


class TestExpireOffers:
    def test_expires_only_lapsed_offers_and_is_idempotent(self):
        lapsed, fresh = offered(), offered()
        Application.objects.filter(pk=lapsed.pk).update(
            offer_expires_at=timezone.now() - timedelta(minutes=5)
        )
        assert jobs.expire_offers(timezone.now()) == {"expired": 1, "skipped": 0}
        lapsed.refresh_from_db()
        fresh.refresh_from_db()
        assert lapsed.status == A.EXPIRED and fresh.status == A.OFFERED
        assert AuditLog.objects.get(action="application.expired").after["by"] == "system"
        # Both sides hear the offer lapsed.
        notified = set(
            Notification.objects.filter(kind="application.expired").values_list(
                "user_id", flat=True
            )
        )
        assert notified == {lapsed.talent_id, lapsed.gig.vendor_id}
        # A second run finds nothing to do.
        assert jobs.expire_offers(timezone.now()) == {"expired": 0, "skipped": 0}

    def test_offers_dont_expire_early(self):
        application = offered()
        with pytest.raises(Exception, match="hasn't expired"):
            transition(application.pk, A.EXPIRED, actor=Actor.SYSTEM)


class TestStaleInterviews:
    def test_flags_week_old_interviews_once_and_tells_the_vendor(self):
        stale, recent = interviewing(days_ago=8), interviewing(days_ago=2)
        assert jobs.flag_stale_interviews(timezone.now()) == {"flagged": 1}
        stale.refresh_from_db()
        recent.refresh_from_db()
        assert stale.stale_flagged_at and recent.stale_flagged_at is None
        note = Notification.objects.get(kind="application.interview_stale")
        assert note.user_id == stale.gig.vendor_id
        assert jobs.flag_stale_interviews(timezone.now()) == {"flagged": 0}

    def test_moving_on_clears_the_flag(self):
        stale = interviewing(days_ago=8)
        jobs.flag_stale_interviews(timezone.now())
        transition(stale.pk, A.OFFERED, actor=Actor.VENDOR, user=stale.gig.vendor)
        stale.refresh_from_db()
        assert stale.stale_flagged_at is None
        assert STALE_INTERVIEW_AFTER.days == 7


class TestRunner:
    def test_records_each_run(self):
        run = jobs.run("expire_offers", trigger="manual")
        assert run.finished_at and run.result == {"expired": 0, "skipped": 0} and not run.error
        assert JobRun.objects.get().trigger == "manual"

    def test_records_failures_and_reraises(self):
        with (
            mock.patch.dict(
                jobs.JOBS, {"expire_offers": mock.Mock(side_effect=RuntimeError("db down"))}
            ),
            pytest.raises(RuntimeError),
        ):
            jobs.run("expire_offers")
        assert JobRun.objects.get().error == "RuntimeError: db down"

    def test_overlapping_runs_are_skipped(self):
        params = connection.get_connection_params()
        key = jobs.zlib.crc32(b"barterly-job:expire_offers")
        with psycopg.connect(**{k: v for k, v in params.items() if k != "cursor_factory"}) as other:
            other.execute("SELECT pg_advisory_lock(%s)", [key])
            with pytest.raises(jobs.JobAlreadyRunning):
                jobs.run("expire_offers")
        assert jobs.run("expire_offers").finished_at  # free again

    def test_management_command(self):
        out = StringIO()
        call_command("run_job", "flag_stale_interviews", stdout=out)
        assert "flag_stale_interviews: {'flagged': 0}" in out.getvalue()


class TestEndpoint:
    def post(self, job, token=None):
        client = APIClient()
        if token:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client.post(f"/api/v1/jobs/{job}/")

    def test_runs_with_the_scheduler_token(self):
        response = self.post("expire_offers", GOOD_TOKEN)
        assert response.status_code == 200
        assert response.json()["result"] == {"expired": 0, "skipped": 0}
        assert JobRun.objects.get(pk=response.json()["run_id"]).trigger == "scheduler"

    def test_refuses_everyone_else(self):
        assert self.post("expire_offers").status_code == 401
        assert self.post("expire_offers", "forged").status_code == 401
        assert self.post("expire_offers", OTHER_CALLER_TOKEN).status_code == 403
        assert self.post("drop_tables", GOOD_TOKEN).status_code == 404
        assert not JobRun.objects.exists()

    def test_user_tokens_dont_work(self):
        client = APIClient()
        client.force_authenticate(eligible_talent())
        assert client.post("/api/v1/jobs/expire_offers/").status_code == 401


class TestGoogleVerifier:
    claims = {"email": "scheduler@p.iam.gserviceaccount.com", "email_verified": True}

    @override_settings(
        SCHEDULER_AUDIENCE="https://api.example",
        SCHEDULER_INVOKER_EMAIL="scheduler@p.iam.gserviceaccount.com",
    )
    def test_checks_signature_audience_and_caller(self):
        target = "google.oauth2.id_token.verify_oauth2_token"
        with mock.patch(target, return_value=self.claims) as verify:
            assert GoogleOidcVerifier().verify("t") == self.claims
        assert verify.call_args.kwargs["audience"] == "https://api.example"
        with mock.patch(target, return_value={**self.claims, "email": "x@y"}):
            with pytest.raises(SchedulerAuthError) as exc:
                GoogleOidcVerifier().verify("t")
            assert exc.value.status == 403
        with mock.patch(target, side_effect=ValueError("expired")):
            with pytest.raises(SchedulerAuthError) as exc:
                GoogleOidcVerifier().verify("t")
            assert exc.value.status == 401

    @override_settings(
        SCHEDULER_AUDIENCE="", SCHEDULER_TOKEN_VERIFIER="apps.bookings.scheduler.GoogleOidcVerifier"
    )
    def test_unconfigured_is_503(self):
        response = TestEndpoint().post("expire_offers", "anything")
        assert response.status_code == 503
