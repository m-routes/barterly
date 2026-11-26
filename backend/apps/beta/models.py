"""Closed-beta rules: invite codes, and the weekly review of disputes and safety reports.

docs/beta/README.md explains the rules; apps.beta.rules enforces them while the
`closed_beta` flag is on.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

USER = settings.AUTH_USER_MODEL


class InviteRole(models.TextChoices):
    ANY = "", "Anyone"
    VENDOR = "vendor", "Host"
    TALENT = "talent", "Talent"


class InviteCode(models.Model):
    """One code, handed to one property or person (or a few, with max_uses)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=12, unique=True, help_text="Stored without the dash: ABCD2345."
    )
    role = models.CharField(max_length=10, choices=InviteRole.choices, blank=True, default="")
    cohort = models.CharField(
        max_length=40, db_index=True, help_text='The expansion step it belongs to: "wave-1".'
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        help_text="Who it's for, as ops knows them: a property name and town. No phone numbers.",
    )
    max_uses = models.PositiveSmallIntegerField(default=1)
    used = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["cohort", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(used__lte=models.F("max_uses")), name="beta_invite_not_overused"
            )
        ]
        permissions = [
            ("manage_invites", "Can create and revoke closed-beta invite codes"),
            ("review_safety", "Can record the weekly dispute and safety review"),
            ("view_onboarding", "Can see the beta onboarding tracker"),
        ]

    def __str__(self) -> str:
        return self.display

    @property
    def display(self) -> str:
        return f"{self.code[:4]}-{self.code[4:]}"

    def state(self, now=None) -> str:
        now = now or timezone.now()
        if self.revoked_at:
            return "revoked"
        if self.expires_at and self.expires_at <= now:
            return "expired"
        if self.used >= self.max_uses:
            return "used"
        return "open"


class InviteRedemption(models.Model):
    """Who signed up with which code. One per person."""

    id = models.BigAutoField(primary_key=True)
    invite = models.ForeignKey(InviteCode, on_delete=models.PROTECT, related_name="redemptions")
    user = models.OneToOneField(USER, on_delete=models.PROTECT, related_name="beta_invite")
    role = models.CharField(max_length=10)
    redeemed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-redeemed_at"]

    def __str__(self) -> str:
        return f"{self.user_id} used {self.invite}"


class ReviewKind(models.TextChoices):
    DISPUTE = "dispute", "Booking dispute"
    CHAT_REPORT = "chat_report", "Reported chat message"
    REVIEW_REPORT = "review_report", "Reported review"


class ReviewOutcome(models.TextChoices):
    NO_ACTION = "no_action", "Looked at: no action needed"
    ACTION_TAKEN = "action_taken", "Action taken"
    ESCALATED = "escalated", "Escalated (founders, legal or police)"


class SafetyReview(models.Model):
    """The weekly review's record for one dispute or safety report."""

    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=20, choices=ReviewKind.choices)
    object_id = models.CharField(max_length=64)
    week = models.DateField(help_text="The Monday (IST) of the week it was raised.")
    outcome = models.CharField(max_length=20, choices=ReviewOutcome.choices)
    notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-week", "kind"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "object_id"], name="beta_review_once")
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.object_id}: {self.outcome}"
