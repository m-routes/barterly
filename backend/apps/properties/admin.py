from django.contrib import admin

from apps.properties.models import Property, PropertyPhoto


class PhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 0
    fields = ["position", "media", "caption", "latitude", "longitude", "captured_at"]
    readonly_fields = ["media"]


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    """Edits here trigger re-verification like the API does. Removal goes through the API
    (it withdraws verification), so delete is off."""

    list_display = ["name", "vendor", "property_type", "city", "state", "verification_status"]
    list_filter = ["property_type", "state", "verification_status", "women_friendly"]
    search_fields = ["name", "city", "vendor__phone"]
    list_select_related = ["vendor"]
    readonly_fields = ["vendor", "verification_status", "approx_latitude", "approx_longitude"]
    inlines = [PhotoInline]

    def get_queryset(self, request):
        return Property.all_objects.select_related("vendor")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
