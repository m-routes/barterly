from django.apps import AppConfig


class SupportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.support"
    verbose_name = "Support"

    def ready(self) -> None:
        from apps.privacy.services import erasure
        from apps.privacy.services.registry import Section, register_section, register_unexported
        from apps.support import services

        register_section(Section("support_requests", "support.Ticket", "user", ("assigned_to",)))
        register_section(
            Section(
                "support_messages",
                "support.TicketMessage",
                "ticket__user",
                ("author",),
                {"internal": False},
            )
        )
        register_unexported(
            "support.Ticket", "assigned_to", "The staff member handling the request."
        )
        register_unexported(
            "support.TicketMessage",
            "author",
            "Messages are exported with the person's requests; staff authors aren't.",
        )
        erasure.register_anonymiser("support_requests", services.anonymise)
