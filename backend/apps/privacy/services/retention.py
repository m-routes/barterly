"""Retention: how long each kind of data is kept, and the daily purge.

PRIVACY_RETENTION_DAYS (settings) sets the days per kind. purge() runs from the
privacy_retention job (apps.bookings.jobs) and writes one audit entry per kind it
touched, with the count and the cut-off. Kinds kept for legal reasons (ledger,
invoices, agreements, the audit log) are listed in KEPT and never purged here.
"""

from collections.abc import Callable
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.common.services.audit import log_action
from apps.privacy.services import exports

# Kept for as long as the law needs, outside this job. LEGAL REVIEW NEEDED: the periods.
KEPT = {
    "ledger_and_payments": "8 years (Income Tax Act s.44AA, CGST Act s.36): 8 years.",
    "invoices": "8 years (CGST Act s.36).",
    "agreements_and_signatures": "Length of the agreement plus 3 years (Limitation Act).",
    "audit_log": "8 years, the longest of the periods above.",
    "consent_records": "Life of the account plus 8 years, as proof of consent.",
    "kyc": "Status and masked last four only; the provider keeps the rest (its contract).",
}


def _model(label):
    return apps.get_model(label)


def _notifications(cutoff) -> int:
    rows = (
        _model("notifications.Notification")
        .objects.filter(created_at__lt=cutoff)
        .exclude(status="queued")
    )
    return rows.delete()[0]


def _push_devices(cutoff) -> int:
    return _model("notifications.PushDevice").objects.filter(last_seen_at__lt=cutoff).delete()[0]


def _chat_leakage_bodies(cutoff) -> int:
    rows = (
        _model("chat.LeakageEvent").objects.filter(created_at__lt=cutoff).exclude(original_body="")
    )
    return rows.update(original_body="")


def _gateway_payloads(cutoff) -> int:
    count = (
        _model("money.GatewayEvent")
        .objects.filter(received_at__lt=cutoff)
        .exclude(payload={})
        .update(payload={})
    )
    count += (
        _model("billing.WebhookEvent")
        .objects.filter(received_at__lt=cutoff)
        .exclude(payload={})
        .update(payload={})
    )
    return count


def _attendance_locations(cutoff) -> int:
    rows = (
        _model("attendance.AttendancePass")
        .objects.filter(valid_until__lt=cutoff)
        .filter(Q(latitude__isnull=False) | Q(longitude__isnull=False))
    )
    return rows.update(latitude=None, longitude=None, accuracy_m=None)


def _verification_references(cutoff) -> int:
    """The referee's name and phone, once a reference check is long decided."""
    rows = (
        _model("verification.VerificationCase")
        .objects.filter(check_type="reference", updated_at__lt=cutoff)
        .exclude(status__in=("draft", "submitted", "in_review"))
        .exclude(details={})
    )
    return rows.update(details={})


def _job_runs(cutoff) -> int:
    return _model("bookings.JobRun").objects.filter(started_at__lt=cutoff).delete()[0]


PURGES: dict[str, Callable] = {
    "notifications": _notifications,
    "push_devices": _push_devices,
    "chat_leakage_bodies": _chat_leakage_bodies,
    "gateway_payloads": _gateway_payloads,
    "attendance_locations": _attendance_locations,
    "verification_references": _verification_references,
    "job_runs": _job_runs,
}


def purge(now) -> dict[str, int]:
    result = {}
    for kind, fn in PURGES.items():
        days = settings.PRIVACY_RETENTION_DAYS[kind]
        cutoff = now - timedelta(days=days)
        with transaction.atomic():
            count = fn(cutoff)
            if count:
                log_action(
                    actor=None,
                    action="privacy.retention_purge",
                    object_type="privacy.retention",
                    object_id=kind,
                    after={"kind": kind, "count": count, "days": days, "cutoff": cutoff},
                )
        result[kind] = count
    expired = exports.expire_due(now)
    if expired:
        log_action(
            actor=None,
            action="privacy.retention_purge",
            object_type="privacy.retention",
            object_id="data_exports",
            after={
                "kind": "data_exports",
                "count": expired,
                "hours": settings.PRIVACY_EXPORT_KEEP_HOURS,
            },
        )
    result["data_exports"] = expired
    return result
