from django.apps import AppConfig


class BetaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.beta"
    verbose_name = "Closed beta"

    def ready(self) -> None:
        from apps.privacy.services.registry import Section, register_section, register_unexported

        register_section(Section("beta_invite", "beta.InviteRedemption", "user"))
        register_unexported("beta.InviteCode", "created_by", "The staff member who made the code.")
        register_unexported(
            "beta.SafetyReview", "reviewed_by", "The trust team member who reviewed it."
        )
