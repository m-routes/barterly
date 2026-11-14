from django.contrib import admin

from apps.applications.models import Application, ApplicationAttachment


class AttachmentInline(admin.TabularInline):
    model = ApplicationAttachment
    extra = 0
    can_delete = False
    fields = ["position", "kind", "media", "url", "title"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    """Read-only: status changes go through the services, which audit them."""

    list_display = ["id", "gig", "talent", "status", "fit_score", "applied_at"]
    list_filter = ["status"]
    search_fields = ["id", "talent__phone", "gig__title"]
    list_select_related = ["gig", "talent"]
    inlines = [AttachmentInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
