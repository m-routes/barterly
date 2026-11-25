from django.contrib import admin, messages

from apps.beta import invites
from apps.beta.models import InviteCode, InviteRedemption, SafetyReview

PERM = "beta.manage_invites"


class _InviteAdminBase(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.has_perm(PERM)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(PERM)

    def has_add_permission(self, request):
        return False  # made in batches from the back office (Make invite codes)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InviteCode)
class InviteCodeAdmin(_InviteAdminBase):
    list_display = ["display", "cohort", "label", "role", "state", "used", "max_uses", "expires_at"]
    list_filter = ["cohort", "role"]
    search_fields = ["code", "label", "cohort"]
    actions = ["revoke"]

    @admin.display(description="State")
    def state(self, obj):
        return obj.state()

    @admin.action(description="Revoke the selected codes", permissions=["manage"])
    def revoke(self, request, queryset):
        for invite in queryset:
            invites.revoke(invite, by=request.user, reason="revoked in the admin", request=request)
        messages.success(request, f"Revoked {queryset.count()} code(s).")

    def has_manage_permission(self, request):
        return request.user.has_perm(PERM)


@admin.register(InviteRedemption)
class InviteRedemptionAdmin(_InviteAdminBase):
    list_display = ["invite", "user", "role", "redeemed_at"]
    list_select_related = ["invite", "user"]
    search_fields = ["invite__code", "invite__label"]


@admin.register(SafetyReview)
class SafetyReviewAdmin(_InviteAdminBase):
    list_display = ["week", "kind", "object_id", "outcome", "reviewed_by", "reviewed_at"]
    list_filter = ["kind", "outcome", "week"]

    def has_module_permission(self, request):
        return request.user.has_perm("beta.review_safety")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("beta.review_safety")
