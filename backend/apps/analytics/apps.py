from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    verbose_name = "Analytics"

    def ready(self) -> None:
        from apps.analytics import services
        from apps.common.events import subscribe
        from apps.privacy.services import erasure, retention

        subscribe("privacy.consent_changed", services.on_consent_changed)
        # Kept PRIVACY_RETENTION_DAYS["analytics_events"] days, then purged daily.
        retention.PURGES.setdefault("analytics_events", services.purge_older_than)
        erasure.register_anonymiser("analytics_events", lambda user, now: services.forget(user))
