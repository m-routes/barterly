"""Taking product events in, and forgetting them."""

import hashlib
import hmac
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.analytics.events import clean
from apps.analytics.models import AnalyticsEvent
from apps.privacy.models import Purpose
from apps.privacy.services import consents

MAX_BATCH = 50
# Clients queue events offline; older than this, they're not worth keeping.
MAX_AGE = timedelta(days=7)
MAX_SKEW = timedelta(minutes=10)


def actor_key(user) -> str:
    """A stable keyed hash of the user id: the same person links up across events, but
    the table can't be joined back to accounts without the key."""
    key = (settings.ANALYTICS_PSEUDONYM_KEY or settings.SECRET_KEY).encode()
    return hmac.new(key, f"analytics:{user.pk}".encode(), hashlib.sha256).hexdigest()[:32]


def consented(user) -> bool:
    return consents.has_consent(user, Purpose.ANALYTICS)


def _when(value, now: datetime) -> datetime | None:
    when = parse_datetime(value) if isinstance(value, str) else None
    if when is None:
        return now
    if timezone.is_naive(when):
        return None
    if when > now + MAX_SKEW or when < now - MAX_AGE:
        return None
    return when


def ingest(user, events: list, *, platform: str, app_version: str = "", now=None) -> dict:
    """Store the allowed events from one batch. Without consent nothing is stored."""
    now = now or timezone.now()
    if not consented(user):
        return {"accepted": 0, "dropped": len(events), "consent": False}
    actor = actor_key(user)
    rows = []
    for event in events[:MAX_BATCH]:
        if not isinstance(event, dict):
            continue
        props = clean(str(event.get("name", "")), event.get("props"))
        when = _when(event.get("occurred_at"), now)
        if props is None or when is None:
            continue
        rows.append(
            AnalyticsEvent(
                name=event["name"],
                actor=actor,
                role=user.role or "",
                platform=platform,
                app_version=app_version[:20],
                props=props,
                occurred_at=when,
                received_at=now,
            )
        )
    AnalyticsEvent.objects.bulk_create(rows)
    return {"accepted": len(rows), "dropped": len(events) - len(rows), "consent": True}


def forget(user) -> int:
    """Delete everything recorded for this person (consent withdrawn, or erasure)."""
    deleted, _ = AnalyticsEvent.objects.filter(actor=actor_key(user)).delete()
    return deleted


def on_consent_changed(event) -> None:
    """privacy.consent_changed: withdrawing analytics consent deletes the person's events."""
    payload = event.payload
    if payload.get("purpose") == Purpose.ANALYTICS and not payload.get("granted"):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(pk=payload["user_id"]).first()
        if user is not None:
            forget(user)


def purge_older_than(cutoff: datetime) -> int:
    deleted, _ = AnalyticsEvent.objects.filter(occurred_at__lt=cutoff).delete()
    return deleted
