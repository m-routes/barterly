from django.conf import settings
from django.db import models
from django.utils import timezone


class Platform(models.TextChoices):
    ANDROID = "android", "Android"
    IOS = "ios", "iOS"


class AppVersionPolicy(models.Model):
    """Which app versions may still call the API, per platform (docs/api-versioning.md).

    Below `minimum_version` the API answers 426 `upgrade_required` and the app shows a
    blocking update screen. Below `latest_version` the app offers an update it can skip.
    Without a row the settings defaults apply (APP_VERSION_DEFAULTS: nothing is forced).
    """

    platform = models.CharField(max_length=10, choices=Platform.choices, unique=True)
    minimum_version = models.CharField(max_length=20)
    latest_version = models.CharField(max_length=20)
    store_url = models.URLField(max_length=300, blank=True)
    message = models.CharField(
        max_length=300, blank=True, help_text="Shown on the update screen (optional)."
    )
    reason = models.CharField(max_length=300, help_text="Why it was last changed.")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["platform"]
        permissions = [("set_app_version", "Can set the minimum and latest app versions")]

    def __str__(self) -> str:
        return f"{self.platform}: min {self.minimum_version}, latest {self.latest_version}"
