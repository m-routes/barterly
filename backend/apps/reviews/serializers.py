from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.reviews.models import Reply, ReportReason, Review, ReviewStatus
from apps.reviews.services import CATEGORIES, CATEGORY_LABELS

STAR = {"min_value": 1, "max_value": 5}


class ReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = Reply
        fields = ["text", "created_at"]
        read_only_fields = fields


class CategoryScoreSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField(help_text="Depends on who was reviewed.")
    score = serializers.IntegerField()


class StayReviewSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    reply = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "booking_id",
            "subject_side",
            "rating",
            "categories",
            "text",
            "status",
            "author_name",
            "submitted_at",
            "published_at",
            "reply",
        ]
        read_only_fields = fields

    def get_author_name(self, obj) -> str:
        profile = getattr(obj.author, "talent_profile", None) or getattr(
            obj.author, "vendor_profile", None
        )
        for field in ("display_name", "business_name", "name"):
            if value := getattr(profile, field, ""):
                return value
        return "A Barterly member"

    @extend_schema_field(CategoryScoreSerializer(many=True))
    def get_categories(self, obj):
        labels = CATEGORY_LABELS[obj.subject_side]
        return [{"key": c, "label": labels[c], "score": getattr(obj, c)} for c in CATEGORIES]

    @extend_schema_field(ReplySerializer(allow_null=True))
    def get_reply(self, obj):
        answer = getattr(obj, "reply", None)
        if answer is None or answer.status != ReviewStatus.PUBLISHED:
            return None
        return ReplySerializer(answer).data


class WriteReviewSerializer(serializers.Serializer):
    rating = serializers.IntegerField(**STAR)
    communication = serializers.IntegerField(**STAR)
    accuracy = serializers.IntegerField(
        **STAR, help_text="Reviewing a host: accuracy of the listing. A talent: work quality."
    )
    safety = serializers.IntegerField(**STAR)
    reliability = serializers.IntegerField(
        **STAR, help_text="Reviewing a host: payment as agreed. A talent: punctuality."
    )
    text = serializers.CharField(max_length=2000)


class BookingReviewsSerializer(serializers.Serializer):
    """What one side of a booking sees: their own review, and the other's once both are
    published (double-blind)."""

    reviewing = serializers.ChoiceField(choices=["talent", "host"], help_text="Who you review.")
    can_review = serializers.BooleanField()
    window_closes_at = serializers.DateTimeField(allow_null=True)
    category_labels = serializers.DictField(child=serializers.CharField())
    mine = StayReviewSerializer(allow_null=True)
    theirs = StayReviewSerializer(allow_null=True, help_text="Only once published.")
    they_have_reviewed = serializers.BooleanField()


class ReplyRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1000)


class ReportRequestSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReportReason.choices)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ReputationBadgeSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()


class ReputationSerializer(serializers.Serializer):
    rating_average = serializers.DecimalField(max_digits=3, decimal_places=2, allow_null=True)
    review_count = serializers.IntegerField()
    completion_rate = serializers.IntegerField(allow_null=True, help_text="Percent.")
    response_minutes = serializers.IntegerField(
        allow_null=True, help_text="Median chat reply time, last 90 days."
    )
    badges = ReputationBadgeSerializer(many=True)


class UserReputationSerializer(serializers.Serializer):
    talent = ReputationSerializer()
    host = ReputationSerializer()


class ModerationSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["allow", "remove"])
    note = serializers.CharField(max_length=300)


class QueueItemSerializer(StayReviewSerializer):
    flags = serializers.ListField(child=serializers.CharField(), read_only=True)
    reports = serializers.SerializerMethodField()

    class Meta(StayReviewSerializer.Meta):
        fields = [*StayReviewSerializer.Meta.fields, "flags", "reports"]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_reports(self, obj):
        return [
            {"reason": r.reason, "note": r.note, "created_at": r.created_at}
            for r in obj.reports.all()
            if r.resolved_at is None
        ]
