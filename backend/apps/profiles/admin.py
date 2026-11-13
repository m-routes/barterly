from django.contrib import admin

from apps.profiles.models import Skill, TalentProfile, VendorProfile


class ProfileAdmin(admin.ModelAdmin):
    list_select_related = ["user"]
    raw_id_fields = ["user"]
    readonly_fields = ["id", "created_at", "updated_at", "deleted_at"]

    def get_queryset(self, request):
        # Show soft-deleted profiles too, so admins can find and restore them.
        return self.model.all_objects.select_related("user")


@admin.register(TalentProfile)
class TalentProfileAdmin(ProfileAdmin):
    list_display = ["display_name", "talent_type", "user", "home_city", "created_at", "deleted_at"]
    list_filter = ["talent_type"]
    search_fields = ["display_name", "user__phone", "home_city"]
    filter_horizontal = ["skills"]


@admin.register(VendorProfile)
class VendorProfileAdmin(ProfileAdmin):
    list_display = ["business_name", "business_type", "city", "state", "user", "deleted_at"]
    list_filter = ["business_type", "state"]
    search_fields = ["business_name", "user__phone", "city", "gstin"]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}
