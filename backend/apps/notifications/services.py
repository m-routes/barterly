"""Making notifications and delivering them.

notify(): one notification for one person, in their language, with a delivery per channel
they want it on. It runs inside the transaction of the change that caused it; the
deliveries are queued as Cloud Tasks only once that transaction commits.

deliver(): the `notifications.deliver` task. It sends one delivery through its channel's
provider, holding the delivery's row lock so two copies of the task can't both send. A
temporary failure raises RetryLater, and Cloud Tasks retries with backoff; after
MAX_ATTEMPTS the delivery is marked dead (the admin's dead-letter view). A permanent
failure is marked failed at once.

dispatch_due(): the job that queues deliveries whose quiet hours have ended, and any
whose task went missing.
"""

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.common.ops import ops_event
from apps.media.tasks import get_queue, task
from apps.notifications import catalog, templates
from apps.notifications.channels.base import (
    Message,
    PermanentFailure,
    TemporaryFailure,
    available,
    get_provider,
)
from apps.notifications.models import (
    Channel,
    Delivery,
    DeliveryStatus,
    Notification,
    NotificationPreference,
    NotificationSettings,
    NotificationStatus,
    PushDevice,
)

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
TASK = "notifications.deliver"
# Channels quiet hours hold back (in-app and email don't interrupt anyone).
INTERRUPTING = frozenset({Channel.PUSH, Channel.SMS, Channel.WHATSAPP})
OUTWARD = (Channel.PUSH, Channel.EMAIL, Channel.SMS, Channel.WHATSAPP)
# A queued delivery whose task hasn't run by then is queued again by dispatch_due().
LOST_AFTER = timedelta(hours=2)


class RetryLater(Exception):
    """Raised by deliver() for a temporary failure: the task endpoint answers 503 and
    Cloud Tasks tries again with backoff."""


def max_attempts() -> int:
    return settings.NOTIFICATION_MAX_ATTEMPTS


# ---------- Settings ----------


def settings_for(user) -> NotificationSettings:
    found = NotificationSettings.objects.filter(user=user).first()
    return found or NotificationSettings(user=user)


def overrides_for(user) -> dict[tuple[str, str], bool]:
    return {
        (p.event_type, p.channel): p.enabled
        for p in NotificationPreference.objects.filter(user=user)
    }


def quiet_until(prefs: NotificationSettings, now: datetime) -> datetime | None:
    """When quiet hours (India time) end, if `now` falls inside them."""
    if not prefs.quiet_hours_enabled:
        return None
    start, end = _as_time(prefs.quiet_start), _as_time(prefs.quiet_end)
    if start == end:
        return None
    local = now.astimezone(IST)
    t = local.time()
    inside = (start <= t < end) if start < end else (t >= start or t < end)
    if not inside:
        return None
    day = local.date() if t < end else local.date() + timedelta(days=1)
    return datetime.combine(day, end, tzinfo=IST)


def _as_time(value) -> time:
    return value if isinstance(value, time) else time.fromisoformat(str(value))


# ---------- Making notifications ----------


def enrich(kind: str, payload: dict) -> dict:
    """Add what the wording or the links need and the event doesn't carry."""
    extra: dict = {}
    if kind == "application.applied" and "applicant_name" not in payload:
        from apps.profiles.models import TalentProfile

        profile = TalentProfile.objects.filter(user_id=payload.get("talent_id")).first()
        extra["applicant_name"] = (profile.display_name if profile else "") or "Someone"
    if kind.startswith("booking.") and "agreement_id" not in payload and payload.get("booking_id"):
        from apps.agreements.models import Agreement

        agreement = Agreement.objects.filter(booking_id=payload["booking_id"]).first()
        if agreement:
            extra["agreement_id"] = str(agreement.pk)
    return {**payload, **extra}


def notify(
    user,
    kind: str,
    payload: dict,
    *,
    side: str,
    dedup_key: str | None = None,
    now: datetime | None = None,
) -> Notification | None:
    """Make one notification. Returns None when `dedup_key` was already used."""
    now = now or timezone.now()
    if dedup_key and Notification.objects.filter(user=user, dedup_key=dedup_key).exists():
        return None
    prefs = settings_for(user)
    payload = enrich(kind, payload)
    title, body = templates.render(kind, payload, prefs.locale)
    app_path, web_url = catalog.links(kind, side, payload)
    try:
        with transaction.atomic():
            notification = Notification.objects.create(
                user=user,
                kind=kind,
                payload=payload,
                locale=prefs.locale,
                title=title[:200],
                body=body[:1000],
                urgent=catalog.is_urgent(kind),
                app_path=app_path,
                web_url=web_url,
                dedup_key=dedup_key,
                created_at=now,
            )
    except IntegrityError:  # the same key, made a moment ago
        return None
    _make_deliveries(notification, prefs, now=now)
    return notification


def queue_notification(user, kind: str, payload: dict, *, dedup_key: str | None = None):
    """For features that notify someone directly rather than through a domain event
    (saved-search alerts). Talent-side links."""
    return notify(user, kind, payload, side="talent", dedup_key=dedup_key)


def _make_deliveries(notification: Notification, prefs, *, now) -> list[Delivery]:
    wanted = catalog.enabled_channels(notification.kind, overrides_for(notification.user))
    hold = None if notification.urgent else quiet_until(prefs, now)
    deliveries = []
    for channel in Channel.values:
        if channel not in wanted:
            continue
        if channel == Channel.IN_APP:
            deliveries.append(
                Delivery.objects.create(
                    notification=notification,
                    channel=channel,
                    status=DeliveryStatus.SENT,
                    provider="inbox",
                    sent_at=now,
                    created_at=now,
                )
            )
            continue
        if not available(channel):
            continue
        send_after = hold if hold and channel in INTERRUPTING else now
        deliveries.append(
            Delivery.objects.create(
                notification=notification, channel=channel, send_after=send_after, created_at=now
            )
        )
    outward = [d for d in deliveries if d.channel != Channel.IN_APP]
    if not outward:
        notification.status = NotificationStatus.SENT
        notification.sent_at = now
        notification.save(update_fields=["status", "sent_at"])
    for delivery in outward:
        transaction.on_commit(lambda d=delivery: enqueue(d))
    return deliveries


def enqueue(delivery: Delivery, *, now: datetime | None = None) -> None:
    """Hand the delivery to the task queue (Cloud Tasks in production)."""
    now = now or timezone.now()
    delay = max(0, int((delivery.send_after - now).total_seconds()))
    Delivery.objects.filter(pk=delivery.pk).update(enqueued_at=now)
    try:
        get_queue().enqueue(
            TASK,
            {"delivery_id": delivery.pk},
            delay_seconds=delay,
            task_id=f"delivery-{delivery.pk}-{delivery.attempts}-{int(now.timestamp())}",
        )
    except Exception:
        # dispatch_due() picks it up again; the notification itself is safe.
        logger.exception("Couldn't queue a delivery", extra={"delivery_id": delivery.pk})
        Delivery.objects.filter(pk=delivery.pk).update(enqueued_at=None)


# ---------- Delivering ----------


def _recipients(delivery: Delivery) -> tuple[str, ...]:
    user = delivery.notification.user
    if delivery.channel == Channel.PUSH:
        return tuple(
            PushDevice.objects.filter(user=user, disabled_at__isnull=True)
            .order_by("-last_seen_at")
            .values_list("token", flat=True)[:10]
        )
    if delivery.channel == Channel.EMAIL:
        return (user.email,) if user.email else ()
    return (user.phone,) if user.phone else ()


def message_for(delivery: Delivery, to: tuple[str, ...]) -> Message:
    n = delivery.notification
    body = n.body
    if delivery.channel == Channel.SMS:
        body = f"{n.title}: {n.body}"[:140] + (f" {n.web_url}" if n.web_url else "")
    return Message(
        notification_id=str(n.pk),
        kind=n.kind,
        locale=n.locale,
        title=n.title,
        body=body,
        app_path=n.app_path,
        web_url=n.web_url,
        urgent=n.urgent,
        to=to,
        template=templates.whatsapp_template(n.kind, n.locale),
        variables=tuple(templates.whatsapp_variables(n.kind, n.payload, n.locale)),
    )


@task(TASK)
def deliver_task(payload: dict) -> None:
    deliver(payload["delivery_id"])


def deliver(delivery_id, *, now: datetime | None = None) -> Delivery:
    """Send one delivery. Idempotent: anything but a queued, due delivery is left alone."""
    now = now or timezone.now()
    retry: str | None = None
    with transaction.atomic():
        delivery = (
            Delivery.objects.select_for_update(of=("self",))
            .select_related("notification__user")
            .get(pk=delivery_id)
        )
        if delivery.status != DeliveryStatus.QUEUED or delivery.send_after > now:
            return delivery
        delivery.attempts += 1
        provider = get_provider(delivery.channel)
        to = _recipients(delivery)
        if provider is None or not to:
            delivery.status = DeliveryStatus.SKIPPED
            delivery.last_error = (
                "No provider for this channel."
                if provider is None
                else ("Nowhere to send it (no device, email or phone).")
            )
        else:
            delivery.provider = provider.name
            try:
                result = provider.send(message_for(delivery, to))
            except PermanentFailure as exc:
                delivery.status = DeliveryStatus.FAILED
                delivery.last_error = str(exc)[:2000]
            except (TemporaryFailure, Exception) as exc:  # unknown errors are retried too
                delivery.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                if delivery.attempts >= max_attempts():
                    delivery.status = DeliveryStatus.DEAD
                    ops_event(
                        "notification_dead_letter",
                        delivery_id=delivery.pk,
                        channel=delivery.channel,
                        provider=delivery.provider,
                    )
                else:
                    retry = delivery.last_error
            else:
                delivery.status = DeliveryStatus.SENT
                delivery.sent_at = now
                delivery.provider_reference = result.reference[:200]
                delivery.last_error = ""
                if result.dead_tokens:
                    PushDevice.objects.filter(token__in=result.dead_tokens).update(disabled_at=now)
        delivery.save()
        _sync_notification(delivery.notification, now=now)
    if retry:
        raise RetryLater(retry)
    return delivery


def _sync_notification(notification: Notification, *, now) -> None:
    statuses = set(
        notification.deliveries.exclude(channel=Channel.IN_APP).values_list("status", flat=True)
    )
    if statuses & {DeliveryStatus.SENT, DeliveryStatus.READ}:
        status = NotificationStatus.SENT
    elif statuses and statuses <= {
        DeliveryStatus.FAILED,
        DeliveryStatus.DEAD,
        DeliveryStatus.SKIPPED,
    }:
        status = NotificationStatus.FAILED
    else:
        return
    if notification.status != status:
        notification.status = status
        notification.sent_at = notification.sent_at or now
        notification.save(update_fields=["status", "sent_at"])


def requeue(delivery_ids, *, now: datetime | None = None) -> int:
    """Send dead letters (or failed deliveries) again, from the start."""
    now = now or timezone.now()
    count = 0
    for delivery in Delivery.objects.filter(
        pk__in=list(delivery_ids), status__in=(DeliveryStatus.DEAD, DeliveryStatus.FAILED)
    ):
        delivery.status = DeliveryStatus.QUEUED
        delivery.attempts = 0
        delivery.send_after = now
        delivery.save(update_fields=["status", "attempts", "send_after", "updated_at"])
        transaction.on_commit(lambda d=delivery: enqueue(d))
        count += 1
    return count


def dispatch_due(now: datetime) -> dict[str, int]:
    """Job: queue deliveries that are due and have no live task: never queued, queued
    over LOST_AFTER ago, or held for quiet hours and still waiting ten minutes after."""
    lost = (
        Q(enqueued_at__isnull=True)
        | Q(enqueued_at__gte=F("send_after"), enqueued_at__lt=now - LOST_AFTER)
        | Q(enqueued_at__lt=F("send_after"), send_after__lte=now - timedelta(minutes=10))
    )
    due = Delivery.objects.filter(status=DeliveryStatus.QUEUED, send_after__lte=now).filter(lost)
    count = 0
    for delivery in due.order_by("send_after")[:500]:
        enqueue(delivery, now=now)
        count += 1
    return {"queued": count}


# ---------- Reading ----------


def mark_read(user, notification_ids=None, *, from_push: bool = False, now=None) -> int:
    """Mark notifications read (all unread ones when no ids are given)."""
    now = now or timezone.now()
    unread = Notification.objects.filter(user=user, read_at__isnull=True)
    if notification_ids is not None:
        unread = unread.filter(pk__in=list(notification_ids))
    ids = list(unread.values_list("pk", flat=True))
    if not ids:
        return 0
    Notification.objects.filter(pk__in=ids).update(read_at=now)
    channels = [Channel.IN_APP, Channel.PUSH] if from_push else [Channel.IN_APP]
    Delivery.objects.filter(
        notification_id__in=ids, channel__in=channels, status=DeliveryStatus.SENT
    ).update(status=DeliveryStatus.READ, read_at=now)
    return len(ids)
