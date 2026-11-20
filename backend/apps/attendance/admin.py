from django.contrib import admin

from apps.attendance.models import AttendancePass, CheckIn, HourLog


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    """Read-only: check-ins happen through the console (audited)."""

    list_display = [
        "booking",
        "method",
        "checked_in_at",
        "distance_m",
        "flag",
        "reviewed_at",
        "checked_out_at",
    ]
    list_filter = ["method", "flag"]
    search_fields = ["booking__id"]
    readonly_fields = [f.name for f in CheckIn._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HourLog)
class HourLogAdmin(admin.ModelAdmin):
    list_display = ["booking", "day", "minutes", "status", "reviewed_at"]
    list_filter = ["status"]
    readonly_fields = [f.name for f in HourLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendancePass)
class AttendancePassAdmin(admin.ModelAdmin):
    """The code secret stays out of the admin."""

    list_display = ["booking", "issued_at", "valid_from", "valid_until", "located_at"]
    fields = [
        "booking",
        "talent",
        "issued_at",
        "valid_from",
        "valid_until",
        "accuracy_m",
        "located_at",
    ]
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
