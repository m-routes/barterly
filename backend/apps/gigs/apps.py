from django.apps import AppConfig


class GigsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gigs"
    label = "gigs"
    verbose_name = "Gigs"

    def ready(self) -> None:
        from apps.gigs import signals  # noqa: F401 (connects receivers)
