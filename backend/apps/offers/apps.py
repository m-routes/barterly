from django.apps import AppConfig


class OffersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.offers"
    label = "offers"

    def ready(self) -> None:
        from apps.common.events import subscribe
        from apps.offers.services import ENDING_EVENTS, lapse_open_offers

        for name in ENDING_EVENTS:
            subscribe(name, lapse_open_offers)
