"""Support: help and feedback from the apps, answered from the back-office inbox.

docs/beta/support.md has the SLAs and how the inbox is worked.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

USER = settings.AUTH_USER_MODEL


class TicketKind(models.TextChoices):
    HELP = "help", "Help with something"
    PAYMENT = "payment", "Money or payments"
    SAFETY = "safety", "A safety concern"
    BUG = "bug", "Something isn't working"
    FEEDBACK = "feedback", "Feedback or an idea"


class Priority(models.TextChoices):
    URGENT = "urgent", "Urgent"
    NORMAL = "normal", "Normal"
    LOW = "low", "Low"


class TicketStatus(models.TextChoices):
    OPEN = "open", "Waiting for us"
    WAITING = "waiting", "Waiting for the person"
    RESOLVED = "resolved", "Resolved"


class Ticket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="support_tickets")
    kind = models.CharField(max_length=10, choices=TicketKind.choices)
    subject = models.CharField(max_length=120)
    status = models.CharField(
        max_length=10, choices=TicketStatus.choices, default=TicketStatus.OPEN, db_index=True
    )
    priority = models.CharField(max_length=10, choices=Priority.choices)
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    screen = models.CharField(
        max_length=60, blank=True, help_text="Where in the app it was sent from."
    )
    platform = models.CharField(max_length=10, blank=True)
    app_version = models.CharField(max_length=20, blank=True)
    assigned_to = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(default=timezone.now)
    first_response_due = models.DateTimeField()
    resolve_due = models.DateTimeField(null=True, blank=True)
    first_responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at"]
        permissions = [
            ("handle_tickets", "Can answer and resolve support requests"),
            ("view_timeline", "Can see a person's full timeline for support"),
        ]

    def __str__(self) -> str:
        return f"{self.reference}: {self.subject}"

    @property
    def reference(self) -> str:
        return f"S-{str(self.pk)[:8].upper()}"

    def overdue(self, now=None) -> str:
        """ "first_response" or "resolution" when an SLA is missed, else ""."""
        now = now or timezone.now()
        if self.status == TicketStatus.RESOLVED:
            return ""
        if self.first_responded_at is None and self.first_response_due < now:
            return "first_response"
        if self.resolve_due and self.resolve_due < now:
            return "resolution"
        return ""


class TicketMessage(models.Model):
    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL, related_name="+")
    from_staff = models.BooleanField(default=False)
    internal = models.BooleanField(default=False, help_text="A staff note the person never sees.")
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"Message on {self.ticket_id}"


class CannedResponse(models.Model):
    """A reply staff start from. Both languages, so a Hindi speaker gets Hindi."""

    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=80, unique=True)
    kind = models.CharField(
        max_length=10, choices=TicketKind.choices, blank=True, help_text="Empty: any kind."
    )
    body_en = models.TextField()
    body_hi = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "title"]

    def __str__(self) -> str:
        return self.title

    def body_for(self, locale: str) -> str:
        return self.body_hi if locale == "hi" and self.body_hi else self.body_en
