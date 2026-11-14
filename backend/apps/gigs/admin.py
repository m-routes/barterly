from django.contrib import admin

from apps.gigs.models import Gig


@admin.register(Gig)
class GigAdmin(admin.ModelAdmin):
    """Read-only: status changes go through the API, which checks the rules and audits."""

    list_display = ["title", "vendor", "property", "compensation_model", "status", "apply_by"]
    list_filter = ["status", "compensation_model", "role_template"]
    search_fields = ["title", "vendor__phone", "property__name"]
    list_select_related = ["vendor", "property"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
