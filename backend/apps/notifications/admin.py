from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "kind", "status", "sent_at"]
    list_filter = ["kind", "status"]
    search_fields = ["user__phone"]
    list_select_related = ["user"]
    readonly_fields = ["user", "kind", "payload", "status", "created_at", "sent_at"]

    def has_add_permission(self, request):
        return False
