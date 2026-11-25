"""Product analytics (only with consent) and daily KPI snapshots.

An AnalyticsEvent never names a person: `actor` is a keyed hash of the user id, there is
no IP, device id or user agent, and each event's properties are limited to the allowlist
in events.py. Events are only taken from people who said yes to "analytics"
(privacy.Purpose.ANALYTICS); withdrawing deletes theirs. docs/beta/analytics.md has more.
"""

from django.db import models
from django.utils import timezone


class Platform(models.TextChoices):
    WEB = "web", "Web"
    ANDROID = "android", "Android"
    IOS = "ios", "iOS"


class AnalyticsEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=40)
    actor = models.CharField(max_length=32, db_index=True, help_text="Keyed hash, not a user id.")
    role = models.CharField(max_length=10, blank=True)
    platform = models.CharField(max_length=10, choices=Platform.choices)
    app_version = models.CharField(max_length=20, blank=True)
    props = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["name", "occurred_at"], name="analytics_name_time_idx")]
        permissions = [("view_kpis", "Can see the beta KPI dashboard")]

    def __str__(self) -> str:
        return f"{self.name} at {self.occurred_at:%Y-%m-%d %H:%M}"


class KpiSnapshot(models.Model):
    """The KPIs for the window ending on `day`, kept so the dashboard can show a trend."""

    id = models.BigAutoField(primary_key=True)
    day = models.DateField()
    window_days = models.PositiveSmallIntegerField()
    metrics = models.JSONField()
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-day"]
        constraints = [
            models.UniqueConstraint(fields=["day", "window_days"], name="analytics_snapshot_once")
        ]

    def __str__(self) -> str:
        return f"KPIs to {self.day} ({self.window_days} days)"
