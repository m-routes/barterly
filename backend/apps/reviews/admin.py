from django.contrib import admin, messages

from apps.reviews import services
from apps.reviews.models import Reply, Reputation, Review, ReviewReport


class ReportInline(admin.TabularInline):
    model = ReviewReport
    fields = ["reporter", "reason", "note", "created_at", "resolved_at"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Moderation: select reviews and allow or remove them (audited, with a note)."""

    list_display = [
        "booking",
        "subject_side",
        "rating",
        "status",
        "flags",
        "submitted_at",
        "published_at",
    ]
    list_filter = ["status", "subject_side", "rating"]
    search_fields = ["booking__id", "text"]
    readonly_fields = [f.name for f in Review._meta.fields]
    inlines = [ReportInline]
    actions = ["allow", "remove"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _decide(self, request, queryset, decision):
        if not request.user.has_perm("reviews.moderate_review"):
            self.message_user(request, "You can't moderate reviews.", messages.ERROR)
            return
        done = 0
        for review in queryset:
            try:
                services.moderate(
                    review.pk,
                    admin=request.user,
                    decision=decision,
                    note=f"{decision.title()}ed in the admin",
                    request=request,
                )
                done += 1
            except services.ReviewError as exc:
                self.message_user(request, f"{review.pk}: {exc.message}", messages.WARNING)
        self.message_user(request, f"{decision.title()}ed {done} review(s).")

    @admin.action(description="Allow the selected reviews")
    def allow(self, request, queryset):
        self._decide(request, queryset, "allow")

    @admin.action(description="Remove the selected reviews")
    def remove(self, request, queryset):
        self._decide(request, queryset, "remove")


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ["review", "status", "created_at"]
    readonly_fields = [f.name for f in Reply._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(Reputation)
class ReputationAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "side",
        "rating_average",
        "review_count",
        "completion_rate",
        "response_minutes",
    ]
    readonly_fields = [f.name for f in Reputation._meta.fields]

    def has_add_permission(self, request):
        return False
