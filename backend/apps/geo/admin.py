from django.contrib import admin

from apps.geo.models import GeocodeResult


@admin.register(GeocodeResult)
class GeocodeResultAdmin(admin.ModelAdmin):
    list_display = ["query", "provider", "found", "latitude", "longitude", "hits", "fetched_at"]
    list_filter = ["provider", "found"]
    search_fields = ["query", "display_name"]
    readonly_fields = [f.name for f in GeocodeResult._meta.fields]

    def has_add_permission(self, request):
        return False
