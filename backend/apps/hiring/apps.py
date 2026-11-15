from django.apps import AppConfig


class HiringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.hiring"
    label = "hiring"

    def ready(self) -> None:
        from apps.common.events import subscribe
        from apps.hiring.services import close_interviews_when_application_moves_on

        subscribe("application.", close_interviews_when_application_moves_on)
