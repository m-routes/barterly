from django.contrib import admin

from apps.deliverables.models import Deliverable, PostStats, Submission


class SubmissionInline(admin.TabularInline):
    model = Submission
    fields = [
        "version",
        "post_url",
        "disclosure_confirmed",
        "disclosure_detected",
        "submitted_at",
        "review",
        "review_note",
    ]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Deliverable)
class DeliverableAdmin(admin.ModelAdmin):
    """Read-only: deliverables change through the app (audited)."""

    list_display = ["title", "booking", "kind", "status", "due_date", "change_rounds"]
    list_filter = ["status", "kind", "platform"]
    search_fields = ["booking__id", "title"]
    readonly_fields = [f.name for f in Deliverable._meta.fields]
    inlines = [SubmissionInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PostStats)
class PostStatsAdmin(admin.ModelAdmin):
    list_display = ["deliverable", "source", "views", "likes", "comments", "captured_at"]
    list_filter = ["source"]
    readonly_fields = [f.name for f in PostStats._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
