import json

from django.contrib import admin
from django.utils.html import format_html

from apps.common.models import AuditLog

AUDIT_PERMISSION = "backoffice.view_audit_log"
EMPTY = "\u2013"


class ActionGroupFilter(admin.SimpleListFilter):
    """Filter by the first part of the action, e.g. every verification.* entry."""

    title = "area"
    parameter_name = "area"

    def lookups(self, request, model_admin):
        areas = sorted(
            {
                a.split(".", 1)[0]
                for a in AuditLog.objects.values_list("action", flat=True).distinct()
            }
        )
        return [(a, a) for a in areas]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(action__startswith=f"{self.value()}.")
        return queryset


class ActorKindFilter(admin.SimpleListFilter):
    title = "who"
    parameter_name = "who"

    def lookups(self, request, model_admin):
        return [
            ("system", "System (no person)"),
            ("admin", "Admins"),
            ("user", "Vendors and talent"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "system":
            return queryset.filter(actor__isnull=True)
        if self.value() == "admin":
            return queryset.filter(actor__role="admin")
        if self.value() == "user":
            return queryset.filter(actor__role__in=["vendor", "talent"])
        return queryset


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """The audit log viewer. Read-only: entries are append-only, written by log_action().

    Visible to roles with backoffice.view_audit_log (see apps/backoffice/roles.py).
    """

    list_display = ["created_at", "action", "object_type", "object_id", "actor", "ip"]
    list_filter = [
        ActionGroupFilter,
        ActorKindFilter,
        "action",
        "object_type",
        ("created_at", admin.DateFieldListFilter),
    ]
    search_fields = ["object_id", "request_id", "action", "actor__phone"]
    date_hierarchy = "created_at"
    list_select_related = ["actor"]
    list_per_page = 100
    fields = [
        "created_at",
        "action",
        "object_type",
        "object_id",
        "actor",
        "before_pretty",
        "after_pretty",
        "ip",
        "request_id",
    ]
    readonly_fields = fields

    @admin.display(description="Before")
    def before_pretty(self, obj):
        return self._pretty(obj.before)

    @admin.display(description="After")
    def after_pretty(self, obj):
        return self._pretty(obj.after)

    @staticmethod
    def _pretty(value):
        if value is None:
            return EMPTY
        return format_html("<pre>{}</pre>", json.dumps(value, indent=2, ensure_ascii=False))

    def has_module_permission(self, request):
        return request.user.has_perm(AUDIT_PERMISSION)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(AUDIT_PERMISSION)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
