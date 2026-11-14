from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.verification.constants import ID_DOCUMENT_CHOICES, BadgeKind, CheckType
from apps.verification.models import Badge, VerificationCase, VerificationDocument
from apps.verification.services.cases import Decision


class DocumentSerializer(serializers.ModelSerializer):
    media_id = serializers.UUIDField(
        source="media.pk", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = VerificationDocument
        fields = [
            "id",
            "document_type",
            "status",
            "masked_value",
            "media_id",
            "metadata",
            "created_at",
        ]
        extra_kwargs = {"masked_value": {"help_text": "Last four characters only."}}


class CaseSerializer(serializers.ModelSerializer):
    documents = DocumentSerializer(many=True, read_only=True)
    property_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = VerificationCase
        fields = [
            "id",
            "check_type",
            "subject_type",
            "property_id",
            "status",
            "reason",
            "details",
            "submitted_at",
            "reviewed_at",
            "approved_at",
            "expires_at",
            "documents",
        ]
        read_only_fields = fields


class BadgeSerializer(serializers.ModelSerializer):
    case_id = serializers.UUIDField(source="case.pk", read_only=True, allow_null=True, default=None)

    class Meta:
        model = Badge
        fields = ["kind", "granted_at", "grant_reason", "case_id"]
        read_only_fields = fields


class CheckSummarySerializer(serializers.Serializer):
    check_type = serializers.ChoiceField(choices=CheckType.choices)
    label = serializers.CharField()
    required = serializers.BooleanField(help_text="Needed for the trusted member badge.")
    badge = serializers.ChoiceField(choices=BadgeKind.choices)
    cases = CaseSerializer(
        many=True, help_text="Empty until started. The property check has one per property."
    )


class MyVerificationSerializer(serializers.Serializer):
    checks = CheckSummarySerializer(many=True)
    badges = BadgeSerializer(many=True, help_text="Active badges.")
    trusted_member = serializers.BooleanField()


# --- Requests ---


class StartIdCheckSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=ID_DOCUMENT_CHOICES)


class KycSessionSerializer(serializers.Serializer):
    reference = serializers.CharField()
    client_token = serializers.CharField(help_text="Pass to the provider's SDK.")
    redirect_url = serializers.URLField(help_text="Or open the provider's hosted page.")
    expires_in_seconds = serializers.IntegerField()


class StartIdCheckResponseSerializer(serializers.Serializer):
    case = CaseSerializer()
    session = KycSessionSerializer()


class BusinessCheckSerializer(serializers.Serializer):
    pan = serializers.CharField(max_length=10, help_text="10 characters, e.g. ABCPE1234F.")
    gstin = serializers.CharField(
        max_length=15,
        required=False,
        allow_blank=True,
        help_text="Optional. Defaults to the GSTIN on your profile.",
    )


class CertificateItemSerializer(serializers.Serializer):
    media_id = serializers.UUIDField(help_text="A confirmed upload of kind 'document'.")
    title = serializers.CharField(max_length=120)


class CertificatesCheckSerializer(serializers.Serializer):
    certificates = CertificateItemSerializer(many=True, min_length=1, max_length=5)


class ReferenceCheckSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    phone = serializers.CharField(max_length=20, help_text="Indian mobile number.")
    relationship = serializers.CharField(max_length=80, help_text="E.g. 'Hostel manager in Goa'.")


class WebhookResponseSerializer(serializers.Serializer):
    outcome = serializers.CharField()


# --- Admin ---


class AdminDocumentSerializer(DocumentSerializer):
    class Meta(DocumentSerializer.Meta):
        fields = [*DocumentSerializer.Meta.fields, "provider", "provider_reference"]


class AdminCaseSerializer(CaseSerializer):
    documents = AdminDocumentSerializer(many=True, read_only=True)
    user_id = serializers.UUIDField(source="user.pk", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    user_role = serializers.CharField(source="user.role", read_only=True)
    reviewer_id = serializers.SerializerMethodField()

    class Meta(CaseSerializer.Meta):
        fields = [*CaseSerializer.Meta.fields, "user_id", "user_phone", "user_role", "reviewer_id"]
        read_only_fields = fields

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_reviewer_id(self, case):
        return case.reviewer_id


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=Decision.CHOICES)
    reason = serializers.CharField(
        max_length=1000,
        required=False,
        allow_blank=True,
        help_text="Required to reject, request changes or revoke. Shown to the user.",
    )
