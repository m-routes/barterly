"""The ops_backlog job: counts of work waiting, logged for Cloud Monitoring.

Every five minutes it writes one `backlog` ops event; monitoring.tf reads each count
into a gauge and alerts when one stays high. Cloud Tasks queue depth is a built-in
metric and isn't repeated here.
"""

from datetime import timedelta

from django.utils import timezone

from apps.common.ops import ops_event

# How old work must be before it counts as stuck.
NOTIFICATION_STUCK_AFTER = timedelta(minutes=15)
PAYOUT_CREATING_STUCK_AFTER = timedelta(minutes=30)
PAYOUT_PROCESSING_STUCK_AFTER = timedelta(hours=24)


def counts(now) -> dict[str, int]:
    from apps.beta import review
    from apps.bookings.models import JobRun
    from apps.money.models import Payout, PayoutAttemptStatus
    from apps.notifications.models import Delivery, DeliveryStatus
    from apps.support import services as support

    return {
        "notifications_stuck": Delivery.objects.filter(
            status=DeliveryStatus.QUEUED, send_after__lte=now - NOTIFICATION_STUCK_AFTER
        ).count(),
        "notifications_dead_24h": Delivery.objects.filter(
            status=DeliveryStatus.DEAD, updated_at__gte=now - timedelta(hours=24)
        ).count(),
        "payouts_stuck": Payout.objects.filter(
            status=PayoutAttemptStatus.CREATING,
            created_at__lte=now - PAYOUT_CREATING_STUCK_AFTER,
        ).count()
        + Payout.objects.filter(
            status=PayoutAttemptStatus.PROCESSING,
            created_at__lte=now - PAYOUT_PROCESSING_STUCK_AFTER,
        ).count(),
        "jobs_failed_24h": JobRun.objects.filter(started_at__gte=now - timedelta(hours=24))
        .exclude(error="")
        .count(),
        # The closed beta: support requests past their SLA, and disputes or safety
        # reports from past weeks that the weekly review hasn't looked at.
        "support_overdue": support.overdue_count(now),
        "safety_reviews_overdue": len(review.overdue(now)),
    }


def report(now=None) -> dict[str, int]:
    result = counts(now or timezone.now())
    ops_event("backlog", **result)
    return result
