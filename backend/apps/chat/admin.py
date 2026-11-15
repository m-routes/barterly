"""Trust review: reported messages and masked contact details. Conversations themselves
aren't browsable here; a report or leakage event shows the message in question."""

from django.contrib import admin
from django.utils import timezone

from apps.chat.models import LeakageEvent, MessageReport, ReviewStatus
from apps.common.services.audit import log_action


def _mark_reviewed(modeladmin, request, queryset):
    now = timezone.now()
    for item in queryset.filter(status=ReviewStatus.OPEN):
        item.status, item.reviewed_at = ReviewStatus.REVIEWED, now
        item.save(update_fields=["status", "reviewed_at"])
        log_action(
            actor=request.user,
            action=f"{item._meta.model_name}.reviewed",
            obj=item,
            before={"status": ReviewStatus.OPEN},
            after={"status": ReviewStatus.REVIEWED},
            request=request,
        )


_mark_reviewed.short_description = "Mark as reviewed"


class _ReviewAdmin(admin.ModelAdmin):
    actions = [_mark_reviewed]
    list_filter = ["status"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MessageReport)
class MessageReportAdmin(_ReviewAdmin):
    list_display = ["created_at", "reason", "reporter", "message_sender", "status"]
    readonly_fields = ["message", "message_body", "reporter", "reason", "note", "status"]
    fields = readonly_fields

    @admin.display(description="Sender")
    def message_sender(self, obj):
        return obj.message.sender

    @admin.display(description="Message as shown")
    def message_body(self, obj):
        return obj.message.body


@admin.register(LeakageEvent)
class LeakageEventAdmin(_ReviewAdmin):
    list_display = ["created_at", "sender", "kinds", "status"]
    readonly_fields = ["sender", "conversation", "kinds", "original_body", "status", "reviewed_at"]
    fields = readonly_fields
