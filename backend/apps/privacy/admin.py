"""Staff tools: suspected minors, correction requests, and read-only views of consent,
exports and deletions. Every decision goes through the services, so it is audited."""

from django.contrib import admin, messages
from django.utils import timezone

from apps.common.services.audit import log_action
from apps.privacy.models import (
    ConsentRecord,
    CorrectionRequest,
    CorrectionStatus,
    DataExport,
    DeletionRequest,
    MinorCase,
    MinorStatus,
)
from apps.privacy.services import minors


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConsentRecord)
class ConsentRecordAdmin(ReadOnlyAdmin):
    list_display = ["user", "purpose", "granted", "version", "source", "recorded_at"]
    list_filter = ["purpose", "granted", "source"]
    search_fields = ["user__id"]


@admin.register(DataExport)
class DataExportAdmin(ReadOnlyAdmin):
    list_display = ["user", "status", "size_bytes", "created_at", "expires_at"]
    list_filter = ["status"]
    exclude = ["object_key"]


@admin.register(DeletionRequest)
class DeletionRequestAdmin(ReadOnlyAdmin):
    list_display = ["user", "status", "requested_at", "scheduled_for", "completed_at"]
    list_filter = ["status"]


@admin.register(CorrectionRequest)
class CorrectionRequestAdmin(admin.ModelAdmin):
    list_display = ["user", "field", "status", "created_at", "resolved_at"]
    list_filter = ["status"]
    fields = ["user", "field", "correct_value", "note", "status", "resolution_note"]
    readonly_fields = ["user", "field", "correct_value", "note", "status"]
    actions = ["mark_done", "mark_rejected"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _resolve(self, request, queryset, to):
        for entry in queryset.filter(status=CorrectionStatus.OPEN):
            entry.status, entry.resolved_at, entry.resolved_by = to, timezone.now(), request.user
            entry.save(update_fields=["status", "resolved_at", "resolved_by"])
            log_action(
                actor=request.user,
                action="privacy.correction_resolved",
                obj=entry,
                before={"status": CorrectionStatus.OPEN},
                after={"status": to},
                request=request,
            )

    @admin.action(description="Mark corrected (make the change first)")
    def mark_done(self, request, queryset):
        self._resolve(request, queryset, CorrectionStatus.DONE)

    @admin.action(description="Mark not changed (add a resolution note first)")
    def mark_rejected(self, request, queryset):
        self._resolve(request, queryset, CorrectionStatus.REJECTED)


@admin.register(MinorCase)
class MinorCaseAdmin(admin.ModelAdmin):
    """Add a case to suspend an account you believe belongs to a minor; then confirm
    (purges their data) or clear it (an adult after all; write why in the note)."""

    list_display = ["user", "source", "status", "detected_at", "decided_at"]
    list_filter = ["status", "source"]
    fields = [
        "user",
        "source",
        "note",
        "status",
        "restriction",
        "detected_at",
        "decided_at",
        "decided_by",
    ]
    raw_id_fields = ["user"]
    actions = ["confirm_minor", "clear_minor"]

    def get_readonly_fields(self, request, obj=None):
        fixed = ["status", "restriction", "detected_at", "decided_at", "decided_by"]
        return [*fixed, "user", "source"] if obj else fixed

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change:
            MinorCase.objects.filter(pk=obj.pk).update(note=obj.note)
            return
        case = minors.flag(obj.user, source=obj.source, note=obj.note, actor=request.user)
        obj.pk = case.pk

    def _decide(self, request, queryset, fn):
        if not request.user.has_perm("privacy.decide_minor_case"):
            self.message_user(request, "You can't decide minor cases.", messages.ERROR)
            return
        for case in queryset.filter(status=MinorStatus.OPEN):
            try:
                fn(case)
            except minors.MinorCaseError as exc:
                self.message_user(request, f"{case.pk}: {exc.message}", messages.WARNING)

    @admin.action(description="Confirm minor: purge their data (can't be undone)")
    def confirm_minor(self, request, queryset):
        self._decide(request, queryset, lambda c: minors.confirm(c.pk, actor=request.user))

    @admin.action(description="Clear: an adult after all (uses the case note as the reason)")
    def clear_minor(self, request, queryset):
        self._decide(
            request, queryset, lambda c: minors.clear(c.pk, actor=request.user, note=c.note)
        )
