from django import forms
from django.contrib import admin

from apps.flags import services
from apps.flags.models import FeatureFlag
from apps.flags.registry import FLAGS


class FlagForm(forms.ModelForm):
    key = forms.ChoiceField(choices=[(k, k) for k in sorted(FLAGS)])

    class Meta:
        model = FeatureFlag
        fields = ["key", "enabled", "reason"]


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    """Changes go through services.set_flag, so they're audited and the cache clears."""

    form = FlagForm
    list_display = ["key", "enabled", "reason", "updated_by", "updated_at"]
    readonly_fields = ["updated_by", "updated_at"]

    def has_module_permission(self, request):
        return request.user.has_perm("flags.toggle_flag")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("flags.toggle_flag")

    def has_add_permission(self, request):
        return request.user.has_perm("flags.toggle_flag")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("flags.toggle_flag")

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        saved = services.set_flag(
            obj.key, obj.enabled, actor=request.user, reason=obj.reason, request=request
        )
        obj.pk = saved.pk
