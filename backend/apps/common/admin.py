from django.contrib import admin

from apps.common.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: entries are append-only and written by log_action()."""

    list_display = ["created_at", "action", "object_type", "object_id", "actor", "ip"]
    list_filter = ["action", "object_type"]
    search_fields = ["object_id", "request_id", "action"]
    date_hierarchy = "created_at"
    list_select_related = ["actor"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
