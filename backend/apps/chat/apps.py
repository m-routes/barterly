from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat"
    label = "chat"

    def ready(self) -> None:
        from apps.chat.services import open_on_shortlist
        from apps.common.events import subscribe

        subscribe("application.shortlisted", open_on_shortlist)
