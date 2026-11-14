from apps.notifications.models import Notification


def queue_notification(user, kind: str, payload: dict) -> Notification:
    """Queue one notification. A Phase 3 worker delivers queued ones."""
    return Notification.objects.create(user=user, kind=kind, payload=payload)
