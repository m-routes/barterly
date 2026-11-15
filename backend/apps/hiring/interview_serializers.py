"""Interview output, shared by the applicant's and the vendor's views. Times are
stored in UTC; each comes as UTC ISO 8601 plus Asia/Kolkata text for display."""

from datetime import UTC

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.hiring.models import Interview, InterviewSlot, InterviewStatus


def ist(moment) -> str:
    from apps.hiring.services import ist as format_ist

    return format_ist(moment)


class InterviewSlotSerializer(serializers.ModelSerializer):
    starts_at = serializers.DateTimeField(default_timezone=UTC, read_only=True)
    starts_at_ist = serializers.SerializerMethodField()

    class Meta:
        model = InterviewSlot
        fields = ["id", "starts_at", "starts_at_ist"]
        read_only_fields = fields

    def get_starts_at_ist(self, slot) -> str:
        return ist(slot.starts_at)


class InterviewSerializer(serializers.ModelSerializer):
    slots = InterviewSlotSerializer(many=True, read_only=True)
    starts_at = serializers.DateTimeField(default_timezone=UTC, read_only=True, allow_null=True)
    starts_at_ist = serializers.SerializerMethodField()
    video_link = serializers.SerializerMethodField(help_text="Shown once a time is picked.")
    timezone = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = [
            "id",
            "status",
            "slots",
            "starts_at",
            "starts_at_ist",
            "duration_minutes",
            "video_link",
            "note",
            "timezone",
            "created_at",
        ]
        read_only_fields = fields

    def get_starts_at_ist(self, interview) -> str:
        return ist(interview.starts_at)

    @extend_schema_field(serializers.URLField(allow_blank=True))
    def get_video_link(self, interview) -> str:
        return interview.video_link if interview.status == InterviewStatus.SCHEDULED else ""

    def get_timezone(self, interview) -> str:
        return "Asia/Kolkata"
