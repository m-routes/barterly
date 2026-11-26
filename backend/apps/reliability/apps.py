from django.apps import AppConfig


class ReliabilityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reliability"
    label = "reliability"

    def ready(self) -> None:
        from apps.common.events import subscribe
        from apps.reliability.services import RECOMPUTE_ON, on_event

        for name in RECOMPUTE_ON:
            subscribe(name, on_event)
