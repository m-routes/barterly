"""Turn domain events into queued notifications for the people they concern.

Runs inside the transaction of the change (see apps.common.events), so a notification
exists exactly when its change does. The notification's kind is the event's name.
"""

from django.contrib.auth import get_user_model

from apps.common.events import DomainEvent, subscribe
from apps.notifications.models import Notification, NotificationStatus
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
    # Offers (apps.offers).
    "offer.countered": (VENDOR,),
    "offer.counter_declined": (TALENT,),
    "offer.held": (TALENT,),
    "offer.reopened": (TALENT,),
    "offer.step_in": (VENDOR,),
    # Bookings (apps.bookings.confirmation and .cancellation).
    "booking.place_opened": (VENDOR,),
}
# Covered by agreement.ready, which both sides get at the same moment.
SILENT = frozenset({"booking.signing"})
# Agreement events both sides hear about; the rest go to the side that didn't act.
AGREEMENT_TO_BOTH = frozenset({"agreement.ready", "agreement.in_force"})


def recipients(event: DomainEvent) -> tuple[str, ...]:
    if event.name in SILENT:
        return ()
    if event.name in APPLICATION_RECIPIENTS:
        sides = APPLICATION_RECIPIENTS[event.name]
        # A lapsed offer: the vendor should know the slot is free again too.
        if event.name == "application.expired" and event.payload.get("from") == "offered":
            sides = (TALENT, VENDOR)
        # The host confirms by accepting the talent's counter: then the talent hears.
        if event.name == "application.confirmed" and event.payload.get("by") == VENDOR:
            sides = (TALENT,)
        return sides
    if event.name in AGREEMENT_TO_BOTH:
        return (TALENT, VENDOR)
    if event.name.startswith(("booking.", "agreement.")):
        # The other side hears about it; changes by the system or an admin go to both.
        by = event.payload.get("by")
        return {TALENT: (VENDOR,), VENDOR: (TALENT,)}.get(by, (TALENT, VENDOR))
    return ()


def notify(event: DomainEvent) -> None:
    ids = [event.payload.get(f"{side}_id") for side in recipients(event)]
    users = get_user_model().objects.filter(pk__in=[i for i in ids if i])
    for user in users:
        queue_notification(user, event.name, event.payload)


def notify_chat_message(event: DomainEvent) -> None:
    """A push for a new chat message. While one for the same conversation is still
    waiting to go out, it's updated (count and latest preview) instead of adding
    another, so a burst of messages is one notification."""
    payload = event.payload
    waiting = (
        Notification.objects.select_for_update()
        .filter(
            user_id=payload["recipient_id"],
            kind=event.name,
            status=NotificationStatus.QUEUED,
            payload__conversation_id=payload["conversation_id"],
        )
        .first()
    )
    if waiting:
        waiting.payload = {**payload, "count": waiting.payload.get("count", 1) + 1}
        waiting.save(update_fields=["payload"])
        return
    user = get_user_model().objects.filter(pk=payload["recipient_id"]).first()
    if user:
        queue_notification(user, event.name, {**payload, "count": 1})


def register() -> None:
    subscribe("application.", notify)
    subscribe("booking.", notify)
    subscribe("interview.", notify)
    subscribe("offer.", notify)
    subscribe("agreement.", notify)
    subscribe("chat.message", notify_chat_message)
