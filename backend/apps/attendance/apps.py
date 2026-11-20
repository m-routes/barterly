from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.attendance"
    label = "attendance"
    verbose_name = "Attendance"

    def ready(self) -> None:
        from apps.attendance import services
        from apps.common.events import subscribe

        subscribe("booking.checked_in", services.on_checked_in)
