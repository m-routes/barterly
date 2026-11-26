from django.contrib import admin

from apps.support.models import CannedResponse


@admin.register(CannedResponse)
class CannedResponseAdmin(admin.ModelAdmin):
    """Support keeps its own replies up to date (support.*_cannedresponse)."""

    list_display = ["title", "kind", "active", "updated_at"]
    list_filter = ["kind", "active"]
    search_fields = ["title", "body_en", "body_hi"]
