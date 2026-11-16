from django.contrib import admin

from apps.agreements.models import Agreement, AgreementVersion, Signature


class ReadOnly(admin.ModelAdmin):
    """Agreements change only through apps.agreements.services."""

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SignatureInline(admin.TabularInline):
    model = Signature
    extra = 0
    fields = ["party", "user", "signed_at", "provider", "phone", "ip", "device", "otp_verified_at"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Agreement)
class AgreementAdmin(ReadOnly):
    list_display = ["id", "booking", "current_version", "created_at"]
    search_fields = ["id", "booking__id"]


@admin.register(AgreementVersion)
class AgreementVersionAdmin(ReadOnly):
    list_display = ["agreement", "number", "status", "template", "pdf_sha256", "created_at"]
    list_filter = ["status", "template"]
    search_fields = ["agreement__id", "pdf_sha256"]
    inlines = [SignatureInline]
