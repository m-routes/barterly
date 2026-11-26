from django.contrib import admin

from apps.reliability.models import ReliabilityScore


@admin.register(ReliabilityScore)
class ReliabilityScoreAdmin(admin.ModelAdmin):
    list_display = ["user", "side", "score", "level", "updated_at"]
    list_filter = ["side", "level"]
    search_fields = ["user__phone"]
    readonly_fields = [f.name for f in ReliabilityScore._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
