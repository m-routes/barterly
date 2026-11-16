from django.contrib import admin

from apps.bookings.models import Booking, BookingEvent, JobRun


class ReadOnly(admin.ModelAdmin):
    """Status changes go through the services (transition table, events, audit)."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EventInline(admin.TabularInline):
    model = BookingEvent
    extra = 0
    fields = ["created_at", "from_state", "to_state", "actor", "actor_user", "reason"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(ReadOnly):
    list_display = ["id", "gig", "talent", "status", "start_date", "end_date", "confirmed_at"]
    list_filter = ["status"]
    search_fields = ["id", "talent__phone", "vendor__phone", "gig__title"]
    list_select_related = ["gig", "talent"]
    inlines = [EventInline]


@admin.register(JobRun)
class JobRunAdmin(ReadOnly):
    list_display = ["job", "started_at", "finished_at", "trigger", "result", "error"]
    list_filter = ["job", "trigger"]
