from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reviews"
    label = "reviews"
    verbose_name = "Reviews and reputation"

    def ready(self) -> None:
        from apps.common.events import subscribe
        from apps.reviews import badges, reputation

        badges.check_rules()  # a bad rule in settings fails at startup, not at 2 a.m.
        for name in reputation.RECOMPUTE_ON:
            subscribe(name, reputation.on_event)
