from rest_framework import serializers

from apps.privacy.models import (
    CLIENT_SOURCES,
    ConsentRecord,
    CorrectionRequest,
    DataExport,
    DeletionRequest,
    Purpose,
)


class ConsentStateSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=Purpose.choices)
    label = serializers.CharField()
    required = serializers.BooleanField(help_text="Needed to use Barterly at all.")
    granted = serializers.BooleanField()
    version = serializers.CharField(help_text='The version agreed to; "" if never asked.')
    current_version = serializers.CharField()
    needs_renewal = serializers.BooleanField(help_text="Given for an older version.")
    recorded_at = serializers.DateTimeField(allow_null=True)


class ConsentChangeSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=Purpose.choices)
    granted = serializers.BooleanField(help_text="true to give, false to withdraw.")
    version = serializers.CharField(
        max_length=40,
        required=False,
        help_text="The document version shown. Required when giving consent.",
    )
    source = serializers.ChoiceField(choices=CLIENT_SOURCES, default="api")

    def validate(self, attrs):
        if attrs["granted"] and not attrs.get("version"):
            raise serializers.ValidationError({"version": "Say which version you agreed to."})
        return attrs


class ConsentRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentRecord
        fields = ["id", "purpose", "granted", "version", "source", "recorded_at"]
        read_only_fields = fields


class PolicyDocumentSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=Purpose.choices)
    label = serializers.CharField()
    version = serializers.CharField()
    required = serializers.BooleanField()
    web_path = serializers.CharField(help_text="Where to read it on the web app.")


class DataExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataExport
        fields = ["id", "status", "size_bytes", "created_at", "expires_at"]
        read_only_fields = fields


class ExportLinkSerializer(serializers.Serializer):
    url = serializers.URLField(help_text="Signed; works once fetched, for a few minutes.")
    expires_in_seconds = serializers.IntegerField()


class BlockerSerializer(serializers.Serializer):
    code = serializers.CharField()
    count = serializers.IntegerField()
    message = serializers.CharField()


class DeletionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeletionRequest
        fields = ["id", "status", "requested_at", "scheduled_for", "cancelled_at", "completed_at"]
        read_only_fields = fields


class DeletionStatusSerializer(serializers.Serializer):
    request = DeletionRequestSerializer(allow_null=True)
    blockers = BlockerSerializer(many=True)
    grace_days = serializers.IntegerField()


class DeletionCreateSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(help_text="Must be true.")
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Confirm that you want your account deleted.")
        return value


class CorrectionCreateSerializer(serializers.Serializer):
    field = serializers.CharField(max_length=60)
    correct_value = serializers.CharField(max_length=500)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class CorrectionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorrectionRequest
        fields = [
            "id",
            "field",
            "correct_value",
            "note",
            "status",
            "created_at",
            "resolved_at",
            "resolution_note",
        ]
        read_only_fields = ["id", "status", "created_at", "resolved_at", "resolution_note"]


class GrievanceOfficerSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(allow_blank=True)
    address = serializers.CharField()
    hours = serializers.CharField()
    acknowledge_hours = serializers.IntegerField()
    resolve_days = serializers.IntegerField()
