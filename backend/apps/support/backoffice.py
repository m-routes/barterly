"""The support inbox, one request's page, and a person's timeline."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from apps.backoffice.views import PAGE_SIZE, _context
from apps.common.services.audit import log_action
from apps.support import services, timeline
from apps.support.forms import StaffReplyForm
from apps.support.models import CannedResponse, Priority, Ticket, TicketKind, TicketStatus

PRIORITY_ORDER = {Priority.URGENT: 0, Priority.NORMAL: 1, Priority.LOW: 2}


@permission_required("support.handle_tickets", raise_exception=True)
def inbox(request):
    now = timezone.now()
    status = request.GET.get("status", "open")
    kind = request.GET.get("kind", "")
    qs = Ticket.objects.select_related("user", "assigned_to")
    if status == "overdue":
        qs = qs.filter(services.overdue_q(now))
    elif status == "mine":
        qs = qs.filter(assigned_to=request.user).exclude(status=TicketStatus.RESOLVED)
    elif status in TicketStatus.values:
        qs = qs.filter(status=status)
    if kind in TicketKind.values:
        qs = qs.filter(kind=kind)
    tickets = sorted(
        qs[:500],
        key=lambda t: (
            not t.overdue(now),
            PRIORITY_ORDER.get(t.priority, 9),
            t.first_response_due
            if t.first_responded_at is None
            else t.resolve_due or t.last_message_at,
        ),
    )
    page = Paginator(tickets, PAGE_SIZE).get_page(request.GET.get("page"))
    return TemplateResponse(
        request,
        "support/inbox.html",
        _context(
            request,
            title="Support inbox",
            page=page,
            rows=[(t, t.overdue(now)) for t in page],
            status=status,
            kind=kind,
            statuses=[
                ("open", "Waiting for us"),
                ("overdue", "Past their SLA"),
                ("mine", "Assigned to me"),
                ("waiting", "Waiting for the person"),
                ("resolved", "Resolved"),
            ],
            kinds=TicketKind.choices,
            overdue_total=services.overdue_count(now),
        ),
    )


@permission_required("support.handle_tickets", raise_exception=True)
def ticket_page(request, ticket_id):
    ticket = get_object_or_404(Ticket.objects.select_related("user", "assigned_to"), pk=ticket_id)
    locale = getattr(getattr(ticket.user, "notification_settings", None), "locale", "en")
    canned = None
    if request.GET.get("canned"):
        canned = CannedResponse.objects.filter(pk=request.GET["canned"], active=True).first()
    initial = {"body": canned.body_for(locale), "canned_id": canned.pk} if canned else {}
    form = StaffReplyForm(request.POST or None, initial=initial)
    if request.method == "POST":
        action = request.POST.get("action", "reply")
        if action == "assign_me":
            services.assign(ticket, to=request.user, staff=request.user, request=request)
            messages.success(request, "Assigned to you.")
            return redirect(reverse("admin:support_ticket", args=[ticket.pk]))
        if action == "resolve":
            services.set_status(ticket, TicketStatus.RESOLVED, staff=request.user, request=request)
            messages.success(request, "Marked resolved.")
            return redirect(reverse("admin:support_ticket", args=[ticket.pk]))
        if form.is_valid():
            try:
                services.reply_as_staff(
                    ticket,
                    staff=request.user,
                    body=form.cleaned_data["body"],
                    internal=form.cleaned_data["internal"],
                    status=form.cleaned_data["status"] or None,
                    canned_id=form.cleaned_data.get("canned_id"),
                    request=request,
                )
            except services.SupportError as exc:
                form.add_error(None, exc.message)
            else:
                messages.success(
                    request, "Note added." if form.cleaned_data["internal"] else "Reply sent."
                )
                return redirect(reverse("admin:support_ticket", args=[ticket.pk]))
    replies = CannedResponse.objects.filter(active=True).filter(kind__in=["", ticket.kind])
    first_sla, resolve_sla = services.sla_for(ticket.priority)
    return TemplateResponse(
        request,
        "support/ticket.html",
        _context(
            request,
            title=f"{ticket.reference}: {ticket.subject}",
            ticket=ticket,
            thread=ticket.messages.select_related("author"),
            form=form,
            replies=replies,
            locale=locale,
            overdue=ticket.overdue(),
            first_sla_hours=int(first_sla.total_seconds() // 3600),
            resolve_sla_hours=int(resolve_sla.total_seconds() // 3600) if resolve_sla else None,
        ),
    )


@permission_required("support.view_timeline", raise_exception=True)
def person_timeline(request, user_id):
    user = get_object_or_404(get_user_model(), pk=user_id)
    chosen = [c for c in request.GET.getlist("show") if c in dict(timeline.CATEGORIES)]
    log_action(
        actor=request.user,
        action="support.timeline_viewed",
        obj=user,
        after={"categories": chosen or "all"},
        request=request,
    )
    entries = timeline.build(user, chosen or None)
    return TemplateResponse(
        request,
        "support/timeline.html",
        _context(
            request,
            title=f"Timeline: {user.phone}",
            header=timeline.header(user),
            entries=entries[:500],
            truncated=len(entries) > 500,
            categories=timeline.CATEGORIES,
            chosen=chosen,
            tickets=Ticket.objects.filter(user=user).order_by("-last_message_at")[:20],
        ),
    )


@permission_required("support.view_timeline", raise_exception=True)
def find_person(request):
    """Look someone up by phone number to open their timeline."""
    from apps.accounts.services.phone import normalize_phone

    phone = request.GET.get("phone", "").strip()
    error = ""
    if phone:
        try:
            normalised = normalize_phone(phone)
        except ValidationError:
            normalised = None
        user = get_user_model().objects.filter(phone=normalised).first() if normalised else None
        if user:
            return redirect(reverse("admin:support_timeline", args=[user.pk]))
        error = "Nobody with that number."
    return TemplateResponse(
        request,
        "support/find_person.html",
        _context(request, title="Find a person", phone=phone, error=error),
    )
