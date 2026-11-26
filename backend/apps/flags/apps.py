from django.apps import AppConfig


class FlagsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.flags"
    verbose_name = "Feature flags"

    def ready(self) -> None:
        from apps.privacy.services.registry import register_unexported

        register_unexported("flags.FeatureFlag", "updated_by", "The staff member who set a flag.")
