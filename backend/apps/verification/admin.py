from django.contrib import admin

from apps.verification.models import Badge, KycWebhookEvent, VerificationCase, VerificationDocument


class ReadOnlyAdmin(admin.ModelAdmin):
    """Read-only: decisions go through the review API, which audit-logs them and keeps
    badges in step."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DocumentInline(admin.TabularInline):
    model = VerificationDocument
    extra = 0
    can_delete = False
    fields = [
        "document_type",
        "status",
        "masked_value",
        "provider",
        "provider_reference",
        "media",
        "metadata",
    ]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(VerificationCase)
class VerificationCaseAdmin(ReadOnlyAdmin):
    list_display = ["id", "user", "check_type", "status", "submitted_at", "reviewer", "expires_at"]
    list_filter = ["status", "check_type"]
    search_fields = ["id", "user__phone", "subject_id"]
    list_select_related = ["user", "reviewer"]
    inlines = [DocumentInline]


@admin.register(Badge)
class BadgeAdmin(ReadOnlyAdmin):
    list_display = ["user", "kind", "granted_at", "revoked_at", "revoke_reason"]
    list_filter = ["kind", ("revoked_at", admin.EmptyFieldListFilter)]
    search_fields = ["user__phone"]
    list_select_related = ["user"]


@admin.register(KycWebhookEvent)
class KycWebhookEventAdmin(ReadOnlyAdmin):
    list_display = ["received_at", "provider", "idempotency_key", "provider_reference", "outcome"]
    list_filter = ["provider", "outcome"]
    search_fields = ["idempotency_key", "provider_reference"]
