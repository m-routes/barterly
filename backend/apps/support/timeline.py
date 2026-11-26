"""A person's whole story in one list, newest first, for support.

It reads what other apps already keep: the audit log (everything the person did, and
everything done to their account), booking status changes on their bookings,
applications, notifications, support requests, consent changes and reports. Opening a
timeline is itself audited, because it shows a lot about one person.
"""

from dataclasses import dataclass
from datetime import datetime
from itertools import chain

from django.db.models import Q
from django.urls import NoReverseMatch, reverse

LIMIT_PER_SOURCE = 200

CATEGORIES = [
    ("activity", "Activity"),
    ("bookings", "Bookings"),
    ("applications", "Applications"),
    ("support", "Support"),
    ("notifications", "Notifications"),
    ("privacy", "Privacy"),
    ("reports", "Reports"),
]


@dataclass
class Entry:
    at: datetime
    category: str
    title: str
    detail: str = ""
    link: str = ""


def _admin(name: str, pk) -> str:
    try:
        return reverse(f"admin:{name}_change", args=[pk])
    except NoReverseMatch:
        return ""


def _short(value, limit=160) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _activity(user) -> list[Entry]:
    from apps.common.models import AuditLog

    entries = (
        AuditLog.objects.filter(
            Q(actor=user) | Q(object_type="accounts.user", object_id=str(user.pk))
        )
        .exclude(action="support.timeline_viewed")
        .select_related("actor")
        .order_by("-created_at")[:LIMIT_PER_SOURCE]
    )
    result = []
    for e in entries:
        by = "" if e.actor_id == user.pk else f" by {e.actor or 'the system'}"
        result.append(
            Entry(
                e.created_at,
                "activity",
                f"{e.action}{by}",
                _short(f"{e.object_type} {e.object_id} {e.after or ''}"),
            )
        )
    return result


def _bookings(user) -> list[Entry]:
    from apps.bookings.models import BookingEvent

    events = (
        BookingEvent.objects.filter(Q(booking__talent=user) | Q(booking__vendor=user))
        .select_related("booking__gig")
        .order_by("-created_at")[:LIMIT_PER_SOURCE]
    )
    return [
        Entry(
            e.created_at,
            "bookings",
            f"Booking {e.from_state or 'new'} → {e.to_state} ({e.actor})",
            _short(f"{e.booking.gig.title}. {e.reason}"),
            _admin("bookings_booking", e.booking_id),
        )
        for e in events
    ]


def _applications(user) -> list[Entry]:
    from apps.applications.models import Application

    apps = (
        Application.objects.filter(Q(talent=user) | Q(gig__vendor=user))
        .select_related("gig")
        .order_by("-created_at")[:LIMIT_PER_SOURCE]
    )
    return [
        Entry(
            a.applied_at or a.created_at,
            "applications",
            f"Application {a.get_status_display().lower()}",
            _short(a.gig.title),
            _admin("applications_application", a.pk),
        )
        for a in apps
    ]


def _support(user) -> list[Entry]:
    from apps.support.models import TicketMessage

    messages = (
        TicketMessage.objects.filter(ticket__user=user)
        .select_related("ticket")
        .order_by("-created_at")[:LIMIT_PER_SOURCE]
    )
    out = []
    for m in messages:
        who = "Staff note" if m.internal else ("Staff replied" if m.from_staff else "They wrote")
        try:
            link = reverse("admin:support_ticket", args=[m.ticket_id])
        except NoReverseMatch:
            link = ""
        out.append(
            Entry(m.created_at, "support", f"{who} on {m.ticket.reference}", _short(m.body), link)
        )
    return out


def _notifications(user) -> list[Entry]:
    from apps.notifications.models import Notification

    return [
        Entry(n.created_at, "notifications", f"Sent: {n.title}", _short(n.body))
        for n in Notification.objects.filter(user=user).order_by("-created_at")[:LIMIT_PER_SOURCE]
    ]


def _privacy(user) -> list[Entry]:
    from apps.privacy.models import ConsentRecord

    return [
        Entry(
            c.recorded_at,
            "privacy",
            f"{'Gave' if c.granted else 'Withdrew'} consent: {c.get_purpose_display()}",
            f"Version {c.version}, from {c.get_source_display()}",
        )
        for c in ConsentRecord.objects.filter(user=user)[:LIMIT_PER_SOURCE]
    ]


def _reports(user) -> list[Entry]:
    from apps.chat.models import MessageReport

    made = MessageReport.objects.filter(reporter=user).order_by("-created_at")[:LIMIT_PER_SOURCE]
    about = MessageReport.objects.filter(message__sender=user).order_by("-created_at")[
        :LIMIT_PER_SOURCE
    ]
    return [
        *(
            Entry(
                r.created_at,
                "reports",
                f"Reported a message: {r.get_reason_display()}",
                _short(r.note),
            )
            for r in made
        ),
        *(
            Entry(
                r.created_at,
                "reports",
                f"Their message was reported: {r.get_reason_display()}",
                _short(r.note),
            )
            for r in about
        ),
    ]


SOURCES = {
    "activity": _activity,
    "bookings": _bookings,
    "applications": _applications,
    "support": _support,
    "notifications": _notifications,
    "privacy": _privacy,
    "reports": _reports,
}


def build(user, categories: list[str] | None = None) -> list[Entry]:
    chosen = [c for c in (categories or SOURCES) if c in SOURCES]
    entries = chain.from_iterable(SOURCES[c](user) for c in chosen)
    return sorted(entries, key=lambda e: e.at, reverse=True)


def header(user) -> dict:
    """The facts support looks for first."""
    from apps.beta.models import InviteRedemption
    from apps.privacy.services import consents
    from apps.support.models import Ticket

    redemption = InviteRedemption.objects.filter(user=user).select_related("invite").first()
    return {
        "user": user,
        "badges": list(user.badges.filter(revoked_at__isnull=True))
        if hasattr(user, "badges")
        else [],
        "invite": redemption.invite if redemption else None,
        "consents": consents.states(user),
        "open_tickets": Ticket.objects.filter(user=user).exclude(status="resolved").count(),
    }
