"""Opening, answering and resolving support requests. Every change is audited."""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.common.services.audit import log_action
from apps.support.models import Priority, Ticket, TicketKind, TicketMessage, TicketStatus

PRIORITY_FOR = {
    TicketKind.SAFETY: Priority.URGENT,
    TicketKind.PAYMENT: Priority.URGENT,
    TicketKind.HELP: Priority.NORMAL,
    TicketKind.BUG: Priority.NORMAL,
    TicketKind.FEEDBACK: Priority.LOW,
}


class SupportError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def sla_for(priority: str) -> tuple[timedelta, timedelta | None]:
    """(first response, resolution) targets, from settings.SUPPORT_SLA_HOURS."""
    first, resolve = settings.SUPPORT_SLA_HOURS[priority]
    return timedelta(hours=first), timedelta(hours=resolve) if resolve else None


def _due(priority: str, now):
    first, resolve = sla_for(priority)
    return now + first, (now + resolve) if resolve else None


def open_ticket(
    user,
    *,
    kind: str,
    subject: str,
    body: str,
    booking=None,
    screen: str = "",
    platform: str = "",
    app_version: str = "",
    request=None,
    now=None,
) -> Ticket:
    now = now or timezone.now()
    if booking is not None and user.pk not in (booking.talent_id, booking.vendor_id):
        raise SupportError("not_your_booking", "That booking isn't one of yours.", 404)
    priority = PRIORITY_FOR[kind]
    first_due, resolve_due = _due(priority, now)
    with transaction.atomic():
        ticket = Ticket.objects.create(
            user=user,
            kind=kind,
            subject=subject.strip()[:120],
            priority=priority,
            booking=booking,
            screen=screen[:60],
            platform=platform[:10],
            app_version=app_version[:20],
            created_at=now,
            last_message_at=now,
            first_response_due=first_due,
            resolve_due=resolve_due,
        )
        TicketMessage.objects.create(ticket=ticket, author=user, body=body.strip(), created_at=now)
        log_action(
            actor=user,
            action="support.ticket_opened",
            obj=ticket,
            after={"kind": kind, "priority": priority, "booking_id": booking and booking.pk},
            request=request,
        )
    return ticket


def reply_as_user(ticket: Ticket, *, user, body: str, request=None, now=None) -> TicketMessage:
    now = now or timezone.now()
    if ticket.user_id != user.pk:
        raise Ticket.DoesNotExist
    with transaction.atomic():
        message = TicketMessage.objects.create(
            ticket=ticket, author=user, body=body.strip(), created_at=now
        )
        before = ticket.status
        ticket.last_message_at = now
        if ticket.status != TicketStatus.OPEN:
            # Back in our court. A resolved request reopened gets a fresh resolution target.
            if ticket.status == TicketStatus.RESOLVED:
                _, ticket.resolve_due = _due(ticket.priority, now)
                ticket.resolved_at = None
            ticket.status = TicketStatus.OPEN
        ticket.save()
        if before != ticket.status:
            log_action(
                actor=user,
                action="support.ticket_reopened",
                obj=ticket,
                before={"status": before},
                after={"status": ticket.status},
                request=request,
            )
    return message


def reply_as_staff(
    ticket: Ticket,
    *,
    staff,
    body: str,
    internal: bool = False,
    status: str | None = None,
    canned_id: int | None = None,
    request=None,
    now=None,
) -> TicketMessage:
    """Answer (or add an internal note). An answer moves the request to "waiting for
    the person" unless another status is given, and notifies them."""
    now = now or timezone.now()
    body = body.strip()
    if not body:
        raise SupportError("empty", "Write a message.")
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
        message = TicketMessage.objects.create(
            ticket=ticket,
            author=staff,
            from_staff=True,
            internal=internal,
            body=body,
            created_at=now,
        )
        before = {"status": ticket.status, "first_responded_at": ticket.first_responded_at}
        if not internal:
            ticket.last_message_at = now
            if ticket.first_responded_at is None:
                ticket.first_responded_at = now
            status = status or TicketStatus.WAITING
        if ticket.assigned_to_id is None:
            ticket.assigned_to = staff
        if status:
            _apply_status(ticket, status, now)
        ticket.save()
        log_action(
            actor=staff,
            action="support.note_added" if internal else "support.replied",
            obj=ticket,
            before=before,
            after={
                "status": ticket.status,
                "first_responded_at": ticket.first_responded_at,
                "canned_id": canned_id,
                "message_id": message.pk,
            },
            request=request,
        )
        if not internal:
            transaction.on_commit(lambda: _notify(ticket))
    return message


def _apply_status(ticket: Ticket, status: str, now) -> None:
    if status not in TicketStatus.values:
        raise SupportError("bad_status", "Unknown status.")
    ticket.status = status
    ticket.resolved_at = now if status == TicketStatus.RESOLVED else None


def set_status(ticket: Ticket, status: str, *, staff, request=None, now=None) -> Ticket:
    now = now or timezone.now()
    with transaction.atomic():
        before = ticket.status
        _apply_status(ticket, status, now)
        ticket.save()
        log_action(
            actor=staff,
            action="support.status_changed",
            obj=ticket,
            before={"status": before},
            after={"status": status},
            request=request,
        )
    return ticket


def assign(ticket: Ticket, *, to, staff, request=None) -> Ticket:
    before = ticket.assigned_to_id
    ticket.assigned_to = to
    ticket.save(update_fields=["assigned_to", "updated_at"])
    log_action(
        actor=staff,
        action="support.assigned",
        obj=ticket,
        before={"assigned_to": before},
        after={"assigned_to": to.pk if to else None},
        request=request,
    )
    return ticket


def _notify(ticket: Ticket) -> None:
    from apps.notifications.services import notify

    side = "vendor" if ticket.user.role == "vendor" else "talent"
    notify(
        ticket.user,
        "support.replied",
        {"ticket_id": str(ticket.pk), "subject": ticket.subject, "reference": ticket.reference},
        side=side,
    )


def overdue_q(now) -> Q:
    return ~Q(status=TicketStatus.RESOLVED) & (
        Q(first_responded_at__isnull=True, first_response_due__lt=now) | Q(resolve_due__lt=now)
    )


def overdue_count(now=None) -> int:
    return Ticket.objects.filter(overdue_q(now or timezone.now())).count()


def anonymise(user, now) -> int:
    """Erasure: keep the record that a request existed, drop what it said."""
    changed = (
        TicketMessage.objects.filter(ticket__user=user)
        .exclude(body="[deleted]")
        .update(body="[deleted]")
    )
    changed += (
        Ticket.objects.filter(user=user)
        .exclude(subject="[deleted]")
        .update(subject="[deleted]", screen="", app_version="")
    )
    return changed
