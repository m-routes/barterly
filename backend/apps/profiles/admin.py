from django.contrib import admin

from apps.profiles.models import TalentProfile, VendorProfile


class ProfileAdmin(admin.ModelAdmin):
    list_select_related = ["user"]
    raw_id_fields = ["user"]
    readonly_fields = ["id", "created_at", "updated_at", "deleted_at"]

    def get_queryset(self, request):
        # Show soft-deleted profiles too, so admins can find and restore them.
        return self.model.all_objects.select_related("user")


@admin.register(TalentProfile)
class TalentProfileAdmin(ProfileAdmin):
    list_display = ["full_name", "user", "home_city", "created_at", "deleted_at"]
    search_fields = ["full_name", "user__phone", "home_city"]


@admin.register(VendorProfile)
class VendorProfileAdmin(ProfileAdmin):
    list_display = ["business_name", "property_type", "city", "state", "user", "deleted_at"]
    list_filter = ["property_type", "state"]
    search_fields = ["business_name", "user__phone", "city", "gstin"]
