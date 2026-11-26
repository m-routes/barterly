from django.contrib import admin

from apps.offers.models import Offer


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    """Read-only: offers change only through apps.offers.services."""

    list_display = ["application", "revision", "proposed_by", "status", "final", "created_at"]
    list_filter = ["status", "proposed_by", "final"]
    search_fields = ["application__id", "terms_sha256"]
    readonly_fields = [f.name for f in Offer._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
