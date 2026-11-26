"""Turn domain events into queued notifications for the people they concern.

Runs inside the transaction of the change (see apps.common.events), so a notification
exists exactly when its change does. The notification's kind is the event's name.
"""

from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef

from apps.common.events import DomainEvent, subscribe
from apps.notifications import services, templates
from apps.notifications.models import Channel, Delivery, DeliveryStatus, Notification

SENT_ALREADY = (
    DeliveryStatus.SENT,
    DeliveryStatus.READ,
    DeliveryStatus.FAILED,
    DeliveryStatus.DEAD,
    DeliveryStatus.SKIPPED,
)

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
    # Reminders (apps.notifications.reminders) name who they're for in "notify".
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


def dedup_key(event: DomainEvent, side: str) -> str:
    """The event's own key when it brings one (reminders do), else one for this event and
    moment: handling the same event twice makes one notification."""
    if key := event.payload.get("dedup_key"):
        return f"{key}:{side}"[:200]
    subject = next(
        (
            event.payload[k]
            for k in ("offer_id", "interview_id", "version_id", "booking_id", "application_id")
            if event.payload.get(k)
        ),
        "",
    )
    return f"{event.name}:{subject}:{event.occurred_at.isoformat()}:{side}"[:200]


def notify(event: DomainEvent) -> None:
    sides = tuple(event.payload.get("notify") or recipients(event))
    ids = {side: event.payload.get(f"{side}_id") for side in sides}
    users = get_user_model().objects.in_bulk([i for i in ids.values() if i])
    for side, user_id in ids.items():
        user = users.get(user_id) or users.get(_uuid(user_id))
        if user:
            services.notify(
                user,
                event.name,
                event.payload,
                side=side,
                dedup_key=dedup_key(event, side),
                now=event.occurred_at,
            )


def _uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def notify_chat_message(event: DomainEvent) -> None:
    """A new chat message. While the recipient hasn't read the last one for this
    conversation and its push hasn't gone out, that notification is updated (count and
    latest preview) instead of adding another: a burst of messages is one push."""
    payload = event.payload
    waiting = (
        Notification.objects.select_for_update()
        .filter(
            user_id=payload["recipient_id"],
            kind=event.name,
            read_at__isnull=True,
            payload__conversation_id=payload["conversation_id"],
        )
        .exclude(
            Exists(
                Delivery.objects.filter(
                    notification=OuterRef("pk"), channel=Channel.PUSH, status__in=SENT_ALREADY
                )
            )
        )
        .first()
    )
    if waiting:
        count = waiting.payload.get("count", 1) + 1
        waiting.payload = {**payload, "count": count}
        title, body = templates.render(event.name, waiting.payload, waiting.locale)
        waiting.title, waiting.body = title[:200], body[:1000]
        waiting.save(update_fields=["payload", "title", "body"])
        return
    user = get_user_model().objects.filter(pk=payload["recipient_id"]).first()
    if user:
        side = "vendor" if getattr(user, "role", "") == "vendor" else "talent"
        services.notify(
            user,
            event.name,
            {**payload, "count": 1},
            side=side,
            dedup_key=f"chat.message:{payload['message_id']}",
            now=event.occurred_at,
        )


def register() -> None:
    subscribe("application.", notify)
    subscribe("booking.", notify)
    subscribe("interview.", notify)
    subscribe("offer.", notify)
    subscribe("agreement.", notify)
    subscribe("chat.message", notify_chat_message)
    subscribe("billing.", notify)
    subscribe("money.", notify)
    subscribe("attendance.", notify)
    subscribe("deliverables.", notify)
    subscribe("reviews.", notify)
