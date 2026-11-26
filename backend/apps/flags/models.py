from django.conf import settings
from django.db import models
from django.utils import timezone


class FeatureFlag(models.Model):
    """A switch for a risky feature, turned off without a deploy (apps.flags.registry)."""

    key = models.CharField(max_length=50, unique=True)
    enabled = models.BooleanField()
    reason = models.CharField(max_length=300, help_text="Why it was last changed.")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["key"]
        permissions = [("toggle_flag", "Can turn feature flags on and off")]

    def __str__(self) -> str:
        return f"{self.key}: {'on' if self.enabled else 'off'}"
