from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig
from django.db.models.signals import post_migrate


class BackofficeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backoffice"
    label = "backoffice"

    def ready(self) -> None:
        from apps.backoffice import signals

        post_migrate.connect(signals.sync_roles_after_migrate, sender=self)


class BarterlyAdminConfig(AdminConfig):
    """django.contrib.admin with Barterly's site (queues and role checks)."""

    default_site = "apps.backoffice.site.BarterlyAdminSite"
