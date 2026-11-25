from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.support.models import Ticket, TicketKind, TicketMessage, TicketStatus


class SupportMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketMessage
        fields = ["id", "from_staff", "body", "created_at"]
        read_only_fields = fields


class SupportTicketSerializer(serializers.ModelSerializer):
    reference = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=TicketStatus.choices, read_only=True)
    kind = serializers.ChoiceField(choices=TicketKind.choices, read_only=True)
    reply_expected_by = serializers.SerializerMethodField(
        help_text="When we aim to answer, while we haven't yet; null once we have."
    )

    class Meta:
        model = Ticket
        fields = [
            "id",
            "reference",
            "kind",
            "subject",
            "status",
            "booking",
            "created_at",
            "last_message_at",
            "reply_expected_by",
        ]
        read_only_fields = fields

    def get_reply_expected_by(self, obj) -> str | None:
        if obj.first_responded_at or obj.status != TicketStatus.OPEN:
            return None
        return serializers.DateTimeField().to_representation(obj.first_response_due)


class SupportTicketDetailSerializer(SupportTicketSerializer):
    messages = serializers.SerializerMethodField()

    class Meta(SupportTicketSerializer.Meta):
        fields = [*SupportTicketSerializer.Meta.fields, "messages"]
        read_only_fields = fields

    @extend_schema_field(SupportMessageSerializer(many=True))
    def get_messages(self, obj) -> list[dict]:
        return SupportMessageSerializer(obj.messages.filter(internal=False), many=True).data


class OpenSupportTicketSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=TicketKind.choices)
    subject = serializers.CharField(max_length=120)
    body = serializers.CharField(max_length=5000)
    booking_id = serializers.UUIDField(required=False, allow_null=True)
    screen = serializers.RegexField(r"^[a-z0-9_/-]{0,60}$", required=False, allow_blank=True)
    platform = serializers.ChoiceField(choices=["web", "android", "ios"], required=False)
    app_version = serializers.CharField(max_length=20, required=False, allow_blank=True)


class SupportReplySerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000)
