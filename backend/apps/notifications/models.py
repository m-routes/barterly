"""Notifications: the in-app inbox item, its deliveries on each channel, and what each
person wants to hear about.

- Notification: one thing someone should know (an event, for one person), rendered in
  their language when it is created. It is their in-app inbox item. `dedup_key` makes
  creating it twice a no-op.
- Delivery: that notification on one channel (in-app, push, email, SMS, WhatsApp). The
  delivery log: queued → sent, or failed (won't retry) or dead (retries used up: the
  dead-letter view in admin), and read when the person opens it.
- NotificationSettings, NotificationPreference: language, quiet hours, and per event type
  and channel on/off (only the choices that differ from the defaults are stored).
- PushDevice: FCM registration tokens.
"""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Channel(models.TextChoices):
    IN_APP = "in_app", "In the app"
    PUSH = "push", "Push"
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"


class Locale(models.TextChoices):
    EN = "en", "English"
    HI = "hi", "हिन्दी (Hindi)"


class NotificationStatus(models.TextChoices):
    """The notification as a whole: queued until a delivery goes out."""

    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=50, help_text="The event type, e.g. 'offer.expiring'.")
    payload = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    status = models.CharField(
        max_length=10, choices=NotificationStatus.choices, default=NotificationStatus.QUEUED
    )
    locale = models.CharField(max_length=5, choices=Locale.choices, default=Locale.EN)
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(max_length=1000, blank=True)
    urgent = models.BooleanField(default=False, help_text="Not held back by quiet hours.")
    app_path = models.CharField(max_length=300, blank=True, help_text="Mobile app route.")
    web_url = models.URLField(max_length=500, blank=True, help_text="Web console page.")
    # NULL, not '', for "no key": the conditional unique constraint skips NULLs.
    dedup_key = models.CharField(  # noqa: DJ001
        max_length=200,
        null=True,
        blank=True,
        help_text="The same key for the same person is one notification, however often "
        "the event is delivered.",
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="notification_queue_idx"),
            models.Index(
                fields=["user", "created_at"],
                condition=Q(read_at__isnull=True),
                name="notification_unread_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dedup_key"],
                condition=Q(dedup_key__isnull=False),
                name="notification_dedup",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} for {self.user_id} ({self.status})"


class DeliveryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed (won't retry)"
    DEAD = "dead", "Dead letter (retries used up)"
    READ = "read", "Read"
    SKIPPED = "skipped", "Skipped (nowhere to send it)"


class Delivery(models.Model):
    id = models.BigAutoField(primary_key=True)
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="deliveries"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(
        max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.QUEUED
    )
    provider = models.CharField(max_length=40, blank=True)
    provider_reference = models.CharField(max_length=200, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    send_after = models.DateTimeField(
        default=timezone.now, help_text="Held back to here by quiet hours, if any."
    )
    enqueued_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "deliveries"
        indexes = [
            models.Index(
                fields=["send_after"],
                condition=Q(status="queued"),
                name="delivery_due_idx",
            ),
            models.Index(fields=["status", "updated_at"], name="delivery_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "channel"], name="delivery_one_per_channel"
            ),
            models.CheckConstraint(
                condition=Q(channel__in=Channel.values), name="delivery_channel_valid"
            ),
            models.CheckConstraint(
                condition=Q(status__in=DeliveryStatus.values), name="delivery_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.notification.kind} by {self.channel} ({self.status})"


class DeadLetter(Delivery):
    """Deliveries whose retries ran out, for the admin's dead-letter view."""

    class Meta:
        proxy = True
        verbose_name = "dead letter"


class NotificationSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="notification_settings",
    )
    locale = models.CharField(max_length=5, choices=Locale.choices, default=Locale.EN)
    quiet_hours_enabled = models.BooleanField(default=True)
    quiet_start = models.TimeField(default="22:00", help_text="India time.")
    quiet_end = models.TimeField(default="08:00", help_text="India time.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "notification settings"

    def __str__(self) -> str:
        return f"Notification settings for {self.user_id}"


class NotificationPreference(models.Model):
    """One choice that differs from the default for an event type on a channel."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_prefs"
    )
    event_type = models.CharField(max_length=50)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    enabled = models.BooleanField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "event_type", "channel"], name="notification_pref_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.event_type} by {self.channel} = {self.enabled}"


class DevicePlatform(models.TextChoices):
    ANDROID = "android", "Android"
    IOS = "ios", "iOS"
    WEB = "web", "Web"


class PushDevice(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_devices"
    )
    token = models.CharField(max_length=500, unique=True)
    platform = models.CharField(max_length=10, choices=DevicePlatform.choices)
    created_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    disabled_at = models.DateTimeField(
        null=True, blank=True, help_text="FCM said the token is no longer valid."
    )

    class Meta:
        indexes = [models.Index(fields=["user"], name="push_device_user_idx")]

    def __str__(self) -> str:
        return f"{self.platform} device of {self.user_id}"
