from django.contrib import admin, messages

from apps.notifications import services
from apps.notifications.models import (
    DeadLetter,
    Delivery,
    DeliveryStatus,
    Notification,
    NotificationSettings,
    PushDevice,
)


class DeliveryInline(admin.TabularInline):
    model = Delivery
    extra = 0
    can_delete = False
    fields = [
        "channel",
        "status",
        "attempts",
        "provider",
        "last_error",
        "send_after",
        "sent_at",
        "read_at",
    ]
    readonly_fields = fields


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "kind", "title", "status", "read_at"]
    list_filter = ["kind", "status", "locale", "urgent"]
    search_fields = ["user__phone", "title", "dedup_key"]
    list_select_related = ["user"]
    readonly_fields = [f.name for f in Notification._meta.fields]
    inlines = [DeliveryInline]

    def has_add_permission(self, request):
        return False


@admin.action(description="Send again from the start")
def send_again(modeladmin, request, queryset):
    count = services.requeue(queryset.values_list("pk", flat=True))
    modeladmin.message_user(request, f"Queued {count} again.", messages.SUCCESS)


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    """The delivery log: every channel of every notification."""

    list_display = [
        "created_at",
        "notification",
        "channel",
        "status",
        "attempts",
        "provider",
        "sent_at",
    ]
    list_filter = ["status", "channel", "provider"]
    search_fields = ["notification__user__phone", "provider_reference", "last_error"]
    list_select_related = ["notification"]
    readonly_fields = [f.name for f in Delivery._meta.fields]
    actions = [send_again]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeadLetter)
class DeadLetterAdmin(DeliveryAdmin):
    """Deliveries whose retries ran out. Fix the cause, then "Send again"."""

    list_display = ["updated_at", "notification", "channel", "attempts", "provider", "last_error"]
    list_filter = ["channel", "provider"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=DeliveryStatus.DEAD)


@admin.register(PushDevice)
class PushDeviceAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "last_seen_at", "disabled_at"]
    list_filter = ["platform"]
    search_fields = ["user__phone"]
    readonly_fields = ["user", "token", "platform", "created_at", "last_seen_at", "disabled_at"]


@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    list_display = ["user", "locale", "quiet_hours_enabled", "quiet_start", "quiet_end"]
    search_fields = ["user__phone"]
