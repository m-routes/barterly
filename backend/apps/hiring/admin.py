from django.contrib import admin

from apps.hiring.models import Interview, InterviewSlot


class SlotInline(admin.TabularInline):
    model = InterviewSlot
    extra = 0
    readonly_fields = ["starts_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    """Read-only: interviews are arranged through the API."""

    list_display = [
        "application",
        "status",
        "starts_at",
        "day_reminder_sent_at",
        "hour_reminder_sent_at",
    ]
    list_filter = ["status"]
    inlines = [SlotInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
