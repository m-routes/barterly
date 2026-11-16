"""In-app chat: one conversation per application. Change it only through
apps.chat.services."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

MAX_BODY = 2000
MAX_ATTACHMENTS = 3


class OpenedBy(models.TextChoices):
    SHORTLIST = "shortlist", "Vendor shortlisted the applicant"
    VENDOR_MESSAGE = "vendor_message", "Vendor messaged the applicant"


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        "applications.Application", on_delete=models.PROTECT, related_name="conversation"
    )
    talent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="talent_conversations"
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vendor_conversations"
    )
    opened_by = models.CharField(max_length=20, choices=OpenedBy.choices)
    opened_at = models.DateTimeField(auto_now_add=True)
    last_seq = models.PositiveIntegerField(
        default=0, help_text="seq of the newest message (the fetch cursor)."
    )
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-opened_at"]
        indexes = [
            models.Index(fields=["talent", "-last_message_at"], name="chat_conv_talent_idx"),
            models.Index(fields=["vendor", "-last_message_at"], name="chat_conv_vendor_idx"),
        ]

    def __str__(self) -> str:
        return f"Chat on {self.application_id}"

    def other(self, user):
        return self.vendor if user.pk == self.talent_id else self.talent

    def has_member(self, user) -> bool:
        return user.pk in (self.talent_id, self.vendor_id)


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    seq = models.PositiveIntegerField(help_text="1, 2, 3... within the conversation.")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="chat_messages"
    )
    body = models.TextField(
        max_length=MAX_BODY, blank=True, help_text="As shown: contact details already masked."
    )
    masked_kinds = models.JSONField(
        default=list, blank=True, help_text="What the leakage guard hid, e.g. ['phone']."
    )
    client_id = models.CharField(
        max_length=64, blank=True, help_text="The sender's id for the send, so retries are safe."
    )
    read_at = models.DateTimeField(null=True, blank=True, help_text="When the other side read it.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["conversation", "seq"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "seq"], name="chat_message_seq_unique"),
            models.UniqueConstraint(
                fields=["conversation", "sender", "client_id"],
                condition=~Q(client_id=""),
                name="chat_message_client_id_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["conversation", "sender"],
                condition=Q(read_at__isnull=True),
                name="chat_message_unread_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.seq} in {self.conversation_id}"


class MessageAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    media = models.ForeignKey(
        "media.MediaFile", on_delete=models.PROTECT, related_name="chat_attachments"
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]

    def __str__(self) -> str:
        return f"{self.media_id} on {self.message_id}"


class Block(models.Model):
    """`blocker` won't hear from `blocked` again: neither can send to the other."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_blocks"
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_blocked_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="chat_block_unique"),
            models.CheckConstraint(
                condition=~Q(blocker=models.F("blocked")), name="chat_block_not_self"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.blocker_id} blocked {self.blocked_id}"


class ReportReason(models.TextChoices):
    SPAM = "spam", "Spam"
    HARASSMENT = "harassment", "Harassment or abuse"
    SCAM = "scam", "Scam or fraud"
    CONTACT = "contact_sharing", "Asking to move off Barterly"
    INAPPROPRIATE = "inappropriate", "Inappropriate content"
    OTHER = "other", "Something else"


class ReviewStatus(models.TextChoices):
    OPEN = "open", "Waiting for review"
    REVIEWED = "reviewed", "Reviewed"


class MessageReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_reports"
    )
    reason = models.CharField(max_length=20, choices=ReportReason.choices)
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["message", "reporter"], name="chat_report_once"),
        ]

    def __str__(self) -> str:
        return f"{self.reason} report on {self.message_id}"


class LeakageEvent(models.Model):
    """A message the contact-sharing guard masked, kept for trust review. The only place
    the original text is stored; only admins can see it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="leakage_events"
    )
    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="leakage_event")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_leakage_events"
    )
    kinds = models.JSONField(help_text="apps.chat.leakage.Kind values found.")
    original_body = models.TextField(max_length=MAX_BODY)
    status = models.CharField(
        max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"], name="chat_leak_review_idx")]

    def __str__(self) -> str:
        return f"{', '.join(self.kinds)} from {self.sender_id}"
