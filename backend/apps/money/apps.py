from django.apps import AppConfig


class MoneyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.money"
    label = "money"
    verbose_name = "Money (ledger and escrow)"

    def ready(self) -> None:
        from apps.common.events import subscribe
        from apps.money import escrow

        subscribe("booking.disputed", escrow.on_booking_event)
        subscribe("booking.cancelled", escrow.on_booking_event)
