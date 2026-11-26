from django.apps import AppConfig


class DeliverablesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.deliverables"
    label = "deliverables"
    verbose_name = "Deliverables"

    def ready(self) -> None:
        from apps.common.events import subscribe
        from apps.deliverables import services

        subscribe("booking.checked_in", services.on_checked_in)
