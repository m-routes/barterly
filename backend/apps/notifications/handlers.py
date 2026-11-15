"""Turn domain events into queued notifications for the people they concern.

Runs inside the transaction of the change (see apps.common.events), so a notification
exists exactly when its change does. The notification's kind is the event's name.
"""

from django.contrib.auth import get_user_model

from apps.common.events import DomainEvent, subscribe
from apps.notifications.services import queue_notification

TALENT, VENDOR = "talent", "vendor"

# Who hears about each application event.
APPLICATION_RECIPIENTS: dict[str, tuple[str, ...]] = {
    "application.applied": (VENDOR,),
    "application.shortlisted": (TALENT,),
    "application.interview": (TALENT,),
    "application.offered": (TALENT,),
    "application.rejected": (TALENT,),
    "application.withdrawn": (VENDOR,),
    "application.declined": (VENDOR,),
    "application.confirmed": (VENDOR,),
    "application.expired": (TALENT,),
    "application.interview_stale": (VENDOR,),
    # Interviews (apps.hiring).
    "interview.proposed": (TALENT,),
    "interview.scheduled": (TALENT, VENDOR),
    "interview.new_times_requested": (VENDOR,),
    "interview.cancelled": (TALENT,),
    "interview.reminder_day": (TALENT, VENDOR),
    "interview.reminder_hour": (TALENT, VENDOR),
}


def recipients(event: DomainEvent) -> tuple[str, ...]:
    if event.name in APPLICATION_RECIPIENTS:
        sides = APPLICATION_RECIPIENTS[event.name]
        # A lapsed offer: the vendor should know the slot is free again too.
        if event.name == "application.expired" and event.payload.get("from") == "offered":
            sides = (TALENT, VENDOR)
        return sides
    if event.name.startswith("booking."):
        # The other side hears about it; changes by the system or an admin go to both.
        by = event.payload.get("by")
        return {TALENT: (VENDOR,), VENDOR: (TALENT,)}.get(by, (TALENT, VENDOR))
    return ()


def notify(event: DomainEvent) -> None:
    ids = [event.payload.get(f"{side}_id") for side in recipients(event)]
    users = get_user_model().objects.filter(pk__in=[i for i in ids if i])
    for user in users:
        queue_notification(user, event.name, event.payload)


def register() -> None:
    subscribe("application.", notify)
    subscribe("booking.", notify)
    subscribe("interview.", notify)
