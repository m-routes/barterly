from django.contrib import admin

from apps.discovery.models import SavedSearch, SavedSearchMatch


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ["name", "talent", "alerts_enabled", "last_checked_at", "created_at"]
    list_filter = ["alerts_enabled"]
    search_fields = ["name", "talent__phone"]
    list_select_related = ["talent"]


@admin.register(SavedSearchMatch)
class SavedSearchMatchAdmin(admin.ModelAdmin):
    list_display = ["saved_search", "gig", "score", "matched_at"]
    list_select_related = ["saved_search", "gig"]
    readonly_fields = ["saved_search", "gig", "score", "breakdown", "matched_at"]
