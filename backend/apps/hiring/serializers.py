"""Vendor-only serializers. Only views that check the requester is the gig's vendor
(or an admin) use these: notes and tags must never reach an applicant."""

from rest_framework import serializers

from apps.applications.serializers import ApplicationListItemSerializer, ApplicationSerializer
from apps.hiring.models import MAX_SLOTS, MAX_TAGS, ApplicationNote, SavedApplicantFilter
from apps.hiring.templates import MAX_MESSAGE, TEMPLATES, VENDOR_REASONS


class NoteSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="author.phone", read_only=True)

    class Meta:
        model = ApplicationNote
        fields = ["id", "body", "author", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class VendorApplicationSerializer(ApplicationSerializer):
    """The applicant view plus the vendor's private notes, tags and rejection code."""

    notes = NoteSerializer(source="private_notes", many=True, read_only=True)
    tags = serializers.SlugRelatedField(
        source="private_tags", slug_field="label", many=True, read_only=True
    )

    class Meta(ApplicationSerializer.Meta):
        fields = [*ApplicationSerializer.Meta.fields, "rejection_code", "notes", "tags"]
        read_only_fields = fields


class VendorApplicationListItemSerializer(ApplicationListItemSerializer):
    tags = serializers.SlugRelatedField(
        source="private_tags", slug_field="label", many=True, read_only=True
    )
    note_count = serializers.IntegerField(read_only=True)
    rejection_code = serializers.CharField(read_only=True)

    class Meta(ApplicationListItemSerializer.Meta):
        fields = [
            *ApplicationListItemSerializer.Meta.fields,
            "rejection_code",
            "tags",
            "note_count",
        ]
        read_only_fields = fields


class BulkSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["shortlist", "reject"])
    application_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=100
    )
    reason_code = serializers.ChoiceField(choices=VENDOR_REASONS, required=False)
    message = serializers.CharField(max_length=MAX_MESSAGE, required=False, allow_blank=True)

    def validate(self, data):
        if data["action"] == "reject" and not data.get("reason_code"):
            raise serializers.ValidationError({"reason_code": ["Pick a reason."]})
        return data


class BulkResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    ok = serializers.BooleanField()
    status = serializers.CharField(allow_blank=True)
    error = serializers.CharField(allow_blank=True)


class TagsSerializer(serializers.Serializer):
    tags = serializers.ListField(
        child=serializers.CharField(max_length=30), max_length=MAX_TAGS, allow_empty=True
    )


class FilterParamsSerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True, help_text="Comma list.")
    min_score = serializers.IntegerField(required=False, min_value=0, max_value=100)
    sort = serializers.ChoiceField(choices=["fit", "newest", "oldest"], required=False)
    tag = serializers.CharField(required=False, max_length=30)


class SavedFilterSerializer(serializers.ModelSerializer):
    params = FilterParamsSerializer()

    class Meta:
        model = SavedApplicantFilter
        fields = ["id", "name", "gig", "params", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_gig(self, gig):
        if gig is not None and gig.vendor_id != self.context["request"].user.pk:
            raise serializers.ValidationError("Pick one of your own gigs.")
        return gig


class RuleSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["language", "skill", "min_followers", "min_stay_days"])
    languages = serializers.ListField(child=serializers.CharField(), required=False)
    skills = serializers.ListField(child=serializers.CharField(), required=False)
    value = serializers.IntegerField(required=False)


class RulesSerializer(serializers.Serializer):
    rules = RuleSerializer(many=True)


class ProposeInterviewSerializer(serializers.Serializer):
    slots = serializers.ListField(
        child=serializers.DateTimeField(),
        min_length=1,
        max_length=MAX_SLOTS,
        help_text="ISO 8601. Times without an offset are read as India time (Asia/Kolkata).",
    )
    video_link = serializers.URLField(max_length=300, help_text="Google Meet, Zoom or similar.")
    duration_minutes = serializers.IntegerField(min_value=10, max_value=180, default=30)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PickSlotSerializer(serializers.Serializer):
    slot_id = serializers.IntegerField()


class NoteInSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ReasonSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    text = serializers.CharField(help_text="What the applicant reads.")


def reasons() -> list[dict]:
    from apps.hiring.templates import RejectionReason

    return [
        {"code": code, "label": RejectionReason(code).label, "text": TEMPLATES[code]}
        for code in VENDOR_REASONS
    ]
