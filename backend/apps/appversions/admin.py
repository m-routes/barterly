from django import forms
from django.contrib import admin

from apps.appversions import services
from apps.appversions.models import AppVersionPolicy

PERM = "appversions.set_app_version"


class AppVersionPolicyForm(forms.ModelForm):
    class Meta:
        model = AppVersionPolicy
        fields = ["platform", "minimum_version", "latest_version", "store_url", "message", "reason"]

    def clean(self):
        data = super().clean()
        minimum = services.parse(data.get("minimum_version", ""))
        latest = services.parse(data.get("latest_version", ""))
        if minimum is None or latest is None:
            raise forms.ValidationError("Versions look like 1.4.2.")
        if latest < minimum:
            raise forms.ValidationError("The latest version can't be older than the minimum.")
        return data


@admin.register(AppVersionPolicy)
class AppVersionPolicyAdmin(admin.ModelAdmin):
    """Changes go through services.set_policy, so they're validated, audited and the
    cache clears."""

    form = AppVersionPolicyForm
    list_display = ["platform", "minimum_version", "latest_version", "updated_by", "updated_at"]
    fields = ["platform", "minimum_version", "latest_version", "store_url", "message", "reason"]

    def has_module_permission(self, request):
        return request.user.has_perm(PERM)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(PERM)

    def has_add_permission(self, request):
        return request.user.has_perm(PERM)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm(PERM)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        saved = services.set_policy(
            obj.platform,
            minimum_version=obj.minimum_version,
            latest_version=obj.latest_version,
            store_url=obj.store_url,
            message=obj.message,
            actor=request.user,
            reason=obj.reason,
            request=request,
        )
        obj.pk = saved.pk
