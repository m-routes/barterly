from django.contrib import admin

from apps.media.models import MediaFile


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    """Read-only: status changes go through the upload services, which audit them."""

    list_display = ["id", "owner", "kind", "status", "scan_status", "size_bytes", "created_at"]
    list_filter = ["kind", "status", "scan_status"]
    search_fields = ["id", "owner__phone", "object_key"]
    list_select_related = ["owner"]

    def get_queryset(self, request):
        return MediaFile.all_objects.select_related("owner")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
