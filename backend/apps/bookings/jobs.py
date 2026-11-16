"""Scheduled jobs, run by Cloud Scheduler through POST /api/v1/jobs/<name>/ (or by
`manage.py run_job <name>`).

Every job is idempotent: it picks rows that are due, then re-checks each one under a
row lock before changing it, so running it twice, or twice at once, changes nothing
the second time. A Postgres advisory lock also stops two runs of the same job from
overlapping. Each run is recorded as a JobRun.
"""

import zlib
from collections.abc import Callable
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from apps.agreements.services import render_pending
from apps.applications import services as applications
from apps.applications.constants import ApplicationStatus
from apps.applications.models import Application
from apps.bookings.cancellation import cancel_unsigned
from apps.bookings.lifecycle import OFFER_TTL, STALE_INTERVIEW_AFTER, Actor
from apps.bookings.models import JobRun
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.discovery.alerts import run_alerts
from apps.gigs.services import close_expired_gigs
from apps.hiring.services import send_reminders
from apps.offers.models import Offer, OfferStatus
from apps.verification.services.cases import expire_due_cases
from apps.verification.services.kyc import sync_pending


def expire_offers(now) -> dict[str, int]:
    """Offers with no reply within 48 hours lapse (offered → expired), as do offers held
    for a place that never opened (their deadline is the stay's start). Bookings still
    awaiting signatures when the stay starts are cancelled."""
    due = Application.objects.filter(
        status=ApplicationStatus.OFFERED, offer_expires_at__lte=now
    ).values_list("pk", flat=True)
    held = set(
        Offer.objects.filter(application_id__in=due, status=OfferStatus.HELD).values_list(
            "application_id", flat=True
        )
    )
    expired = skipped = 0
    for pk in list(due):
        try:
            applications.transition(
                pk,
                ApplicationStatus.EXPIRED,
                actor=Actor.SYSTEM,
                reason=(
                    "No place opened up before the stay."
                    if pk in held
                    else f"No reply within {int(OFFER_TTL.total_seconds() // 3600)} hours."
                ),
                now=now,
            )
            expired += 1
        except applications.InvalidApplicationTransition:
            skipped += 1  # answered (or already expired) since we looked
    return {"expired": expired, "skipped": skipped, **cancel_unsigned(now)}


def flag_stale_interviews(now) -> dict[str, int]:
    """Interviews with no movement for a week are flagged once, and the vendor is told."""
    cutoff = now - STALE_INTERVIEW_AFTER
    from apps.hiring.models import Interview, InterviewStatus

    # Not stale if an interview is booked for the future or happened this week.
    recent_interview = Interview.objects.filter(
        status=InterviewStatus.SCHEDULED, starts_at__gte=cutoff
    ).values("application_id")
    due = (
        Application.objects.filter(
            status=ApplicationStatus.INTERVIEW,
            status_changed_at__lte=cutoff,
            stale_flagged_at__isnull=True,
        )
        .exclude(pk__in=recent_interview)
        .values_list("pk", flat=True)
    )
    flagged = 0
    for pk in list(due):
        with transaction.atomic():
            application = applications.lock(pk)
            still_due = (
                application.status == ApplicationStatus.INTERVIEW
                and application.stale_flagged_at is None
                and application.status_changed_at is not None
                and application.status_changed_at <= cutoff
            )
            if not still_due:
                continue
            application.stale_flagged_at = now
            application.save(update_fields=["stale_flagged_at", "updated_at"])
            log_action(
                actor=None,
                action="application.interview_stale",
                obj=application,
                after={"stale_flagged_at": now, "interview_since": application.status_changed_at},
            )
            publish(
                DomainEvent(
                    "application.interview_stale",
                    {
                        "application_id": str(application.pk),
                        "gig_id": str(application.gig_id),
                        "gig_title": application.gig.title,
                        "talent_id": str(application.talent_id),
                        "vendor_id": str(application.gig.vendor_id),
                        "interview_since": application.status_changed_at,
                    },
                    occurred_at=now,
                )
            )
            flagged += 1
    return {"flagged": flagged}


JOBS: dict[str, Callable[..., dict]] = {
    "expire_offers": expire_offers,
    "flag_stale_interviews": flag_stale_interviews,
    "close_expired_gigs": lambda now: {"closed": close_expired_gigs(timezone.localdate(now))},
    "expire_verifications": lambda now: {"expired": expire_due_cases(now)},
    "sync_kyc_results": lambda now: sync_pending(timedelta(minutes=30)),
    "run_search_alerts": lambda now: run_alerts(now),
    "send_interview_reminders": lambda now: send_reminders(now),
    "render_agreements": render_pending,
}


class JobAlreadyRunning(Exception):
    pass


def run(name: str, *, trigger: str = "scheduler", now=None) -> JobRun:
    """Run one job under an advisory lock and record it. Re-raises job errors (after
    recording them) so the scheduler retries."""
    job = JOBS[name]
    key = zlib.crc32(f"barterly-job:{name}".encode())
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        if not cursor.fetchone()[0]:
            raise JobAlreadyRunning(name)
    record = JobRun.objects.create(job=name, trigger=trigger)
    try:
        record.result = job(now or timezone.now())
    except Exception as exc:
        record.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record.finished_at = timezone.now()
        record.save(update_fields=["result", "error", "finished_at"])
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
    return record
