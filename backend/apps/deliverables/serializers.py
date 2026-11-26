from datetime import timedelta

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.deliverables import services
from apps.deliverables.models import (
    MAX_CHANGE_ROUNDS,
    Deliverable,
    PostStats,
    StatsSource,
    Status,
    Submission,
)
from apps.media.storage import get_storage
from apps.offers.terms import UsageRightsSerializer

LINK_TTL = timedelta(minutes=10)
EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "application/pdf": "pdf",
}


class FileLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    content_type = serializers.CharField()
    size_bytes = serializers.IntegerField()
    url = serializers.URLField(help_text="Valid for 10 minutes.")


def file_links(files, *, attachment: bool, name: str) -> list[dict]:
    storage = get_storage()
    return [
        {
            "id": f.pk,
            "content_type": f.content_type,
            "size_bytes": f.size_bytes,
            "url": storage.signed_read_url(
                f.object_key,
                expires=LINK_TTL,
                download_name=f"{name}-{i}.{EXTENSIONS.get(f.content_type, 'bin')}",
                attachment=attachment,
            ),
        }
        # In the order they were uploaded.
        for i, f in enumerate(sorted(files, key=lambda m: (m.created_at, str(m.pk))), start=1)
        if f.status == "ready"
    ]


class SubmissionSerializer(serializers.ModelSerializer):
    files = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            "version",
            "post_url",
            "files",
            "note",
            "disclosure_confirmed",
            "disclosure_detected",
            "submitted_at",
            "review",
            "review_note",
            "reviewed_at",
        ]
        read_only_fields = fields

    @extend_schema_field(FileLinkSerializer(many=True))
    def get_files(self, obj) -> list[dict]:
        return file_links(obj.files.all(), attachment=False, name=f"v{obj.version}")


class PostStatsSerializer(serializers.ModelSerializer):
    self_reported = serializers.BooleanField(read_only=True)
    screenshot_url = serializers.SerializerMethodField()

    class Meta:
        model = PostStats
        fields = [
            "source",
            "self_reported",
            "views",
            "likes",
            "comments",
            "captured_at",
            "screenshot_url",
        ]
        read_only_fields = fields

    def get_screenshot_url(self, obj) -> str | None:
        if obj.screenshot is None or obj.screenshot.status != "ready":
            return None
        return get_storage().signed_read_url(obj.screenshot.object_key, expires=LINK_TTL)


def latest_stats(deliverable: Deliverable) -> list[PostStats]:
    """The newest snapshot from the platform and the newest self-reported one."""
    found: dict[bool, PostStats] = {}
    for row in deliverable.stats.all():  # newest first
        found.setdefault(row.source == StatsSource.MANUAL, row)
    return [found[k] for k in (False, True) if k in found]


class TrackedDeliverableSerializer(serializers.ModelSerializer):
    booking_id = serializers.UUIDField(read_only=True)
    gig_title = serializers.CharField(source="booking.gig.title", read_only=True)
    change_rounds_left = serializers.SerializerMethodField()
    latest_submission = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    usage_rights = serializers.SerializerMethodField()
    usable_until = serializers.SerializerMethodField()

    class Meta:
        model = Deliverable
        fields = [
            "id",
            "booking_id",
            "gig_title",
            "kind",
            "platform",
            "spec_type",
            "title",
            "notes",
            "due_date",
            "status",
            "change_rounds",
            "change_rounds_left",
            "disclosure_required",
            "submitted_at",
            "approved_at",
            "latest_submission",
            "stats",
            "usage_rights",
            "usable_until",
        ]
        read_only_fields = fields

    def get_change_rounds_left(self, obj) -> int:
        return MAX_CHANGE_ROUNDS - obj.change_rounds

    @extend_schema_field(SubmissionSerializer(allow_null=True))
    def get_latest_submission(self, obj):
        latest = next(iter(obj.submissions.all()), None)
        return SubmissionSerializer(latest).data if latest else None

    @extend_schema_field(PostStatsSerializer(many=True))
    def get_stats(self, obj):
        return PostStatsSerializer(latest_stats(obj), many=True).data

    @extend_schema_field(UsageRightsSerializer(allow_null=True))
    def get_usage_rights(self, obj):
        """Shown once approved: how the host may use it (from the agreement)."""
        if obj.status != Status.APPROVED:
            return None
        return services.usage_rights(obj.booking)

    def get_usable_until(self, obj) -> str | None:
        if obj.status != Status.APPROVED:
            return None
        until = services.usable_until(obj.booking, obj.approved_at)
        return until.isoformat() if until else None


class LibraryItemSerializer(TrackedDeliverableSerializer):
    talent_name = serializers.SerializerMethodField()
    downloads = serializers.SerializerMethodField()

    class Meta(TrackedDeliverableSerializer.Meta):
        fields = [*TrackedDeliverableSerializer.Meta.fields, "talent_name", "downloads"]
        read_only_fields = fields

    def get_talent_name(self, obj) -> str:
        profile = getattr(obj.booking.talent, "talent_profile", None)
        return getattr(profile, "display_name", "") or "Talent"

    @extend_schema_field(FileLinkSerializer(many=True))
    def get_downloads(self, obj):
        approved = next((s for s in obj.submissions.all() if s.review == "approved"), None)
        if approved is None:
            return []
        slug = "".join(ch if ch.isalnum() else "-" for ch in obj.title.lower()).strip("-")
        return file_links(approved.files.all(), attachment=True, name=slug or "content")


class SubmitSerializer(serializers.Serializer):
    post_url = serializers.URLField(max_length=500, required=False, allow_blank=True, default="")
    file_ids = serializers.ListField(
        child=serializers.UUIDField(), max_length=20, required=False, default=list
    )
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    disclosure_confirmed = serializers.BooleanField(
        default=False,
        help_text="The post carries the collaboration label (#collab, #ad or the paid "
        "partnership tag). Required for public posts.",
    )


class ReviewSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class DueDateSerializer(serializers.Serializer):
    due_date = serializers.DateField()


class ManualStatsSerializer(serializers.Serializer):
    views = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)
    likes = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)
    comments = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)
    screenshot_id = serializers.UUIDField(help_text="An uploaded photo of the numbers.")
