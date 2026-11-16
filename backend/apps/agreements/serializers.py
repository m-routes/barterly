from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.agreements import pdf
from apps.agreements.models import Agreement, AgreementVersion, Signature, VersionStatus
from apps.agreements.services import party_of
from apps.offers.models import Party
from apps.offers.terms import (
    CancellationPolicy,
    TermsDeliverableSerializer,
    TermsSerializer,
    UsageRightsSerializer,
)


class SignatureSerializer(serializers.ModelSerializer):
    otp_confirmed = serializers.SerializerMethodField()

    class Meta:
        model = Signature
        fields = ["party", "signed_at", "provider", "otp_confirmed", "document_sha256"]
        read_only_fields = fields

    def get_otp_confirmed(self, signature) -> bool:
        return signature.otp_verified_at is not None


class AgreementVersionSerializer(serializers.ModelSerializer):
    terms = TermsSerializer(read_only=True)
    signatures = SignatureSerializer(many=True, read_only=True)
    proposed_by = serializers.SerializerMethodField(
        help_text="Which side asked for this change; empty for version 1."
    )
    changed_fields = serializers.ListField(
        child=serializers.CharField(), read_only=True, help_text="What this version changes."
    )
    pdf_ready = serializers.BooleanField(source="rendered", read_only=True)
    template_reviewed = serializers.SerializerMethodField(
        help_text="False while the legal text is a placeholder no lawyer has reviewed."
    )
    signed_by_me = serializers.SerializerMethodField()
    can_sign = serializers.SerializerMethodField()

    class Meta:
        model = AgreementVersion
        fields = [
            "id",
            "number",
            "status",
            "status_reason",
            "terms",
            "terms_sha256",
            "changed_fields",
            "change_reason",
            "proposed_by",
            "template",
            "template_reviewed",
            "pdf_ready",
            "pdf_sha256",
            "pdf_size",
            "signatures",
            "signed_by_me",
            "can_sign",
            "created_at",
            "in_force_at",
        ]
        read_only_fields = fields

    def _party(self, version):
        return self.context.get("party")

    @extend_schema_field(serializers.ChoiceField(choices=Party.choices, allow_blank=True))
    def get_proposed_by(self, version) -> str:
        if version.proposed_by_id is None:
            return ""
        return party_of(version.proposed_by, version.agreement.booking) or ""

    def get_template_reviewed(self, version) -> bool:
        return pdf.TEMPLATES[version.template].reviewed

    def get_signed_by_me(self, version) -> bool:
        return any(s.party == self._party(version) for s in version.signatures.all())

    def get_can_sign(self, version) -> bool:
        return (
            version.status == VersionStatus.AWAITING
            and version.rendered
            and not self.get_signed_by_me(version)
        )


class AgreementSerializer(serializers.ModelSerializer):
    booking_status = serializers.CharField(source="booking.status", read_only=True)
    gig_title = serializers.CharField(source="booking.gig.title", read_only=True)
    in_force = serializers.BooleanField(read_only=True)
    current_version = serializers.IntegerField(
        source="current_version.number", read_only=True, allow_null=True, default=None
    )
    my_side = serializers.SerializerMethodField()
    versions = serializers.SerializerMethodField()

    class Meta:
        model = Agreement
        fields = [
            "id",
            "booking",
            "booking_status",
            "gig_title",
            "in_force",
            "current_version",
            "my_side",
            "versions",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ChoiceField(choices=Party.choices))
    def get_my_side(self, agreement) -> str:
        return self.context.get("party", "")

    @extend_schema_field(AgreementVersionSerializer(many=True))
    def get_versions(self, agreement):
        versions = sorted(agreement.versions.all(), key=lambda v: -v.number)
        return AgreementVersionSerializer(versions, many=True, context=self.context).data


class AgreementListItemSerializer(serializers.ModelSerializer):
    booking_status = serializers.CharField(source="booking.status", read_only=True)
    gig_title = serializers.CharField(source="booking.gig.title", read_only=True)
    other_name = serializers.SerializerMethodField()
    start_date = serializers.DateField(source="booking.start_date", read_only=True)
    end_date = serializers.DateField(source="booking.end_date", read_only=True)
    in_force = serializers.BooleanField(read_only=True)
    current_version = serializers.IntegerField(
        source="current_version.number", read_only=True, allow_null=True, default=None
    )
    awaiting_version = serializers.SerializerMethodField(
        help_text="The version waiting for signatures, if any."
    )
    awaiting_my_signature = serializers.SerializerMethodField()

    class Meta:
        model = Agreement
        fields = [
            "id",
            "booking",
            "booking_status",
            "gig_title",
            "other_name",
            "start_date",
            "end_date",
            "in_force",
            "current_version",
            "awaiting_version",
            "awaiting_my_signature",
            "created_at",
        ]
        read_only_fields = fields

    def _awaiting(self, agreement):
        return next(
            (v for v in agreement.versions.all() if v.status == VersionStatus.AWAITING), None
        )

    def get_other_name(self, agreement) -> str:
        from apps.chat.services import display_name

        user = self.context["request"].user
        booking = agreement.booking
        return display_name(booking.talent if booking.vendor_id == user.pk else booking.vendor)

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_awaiting_version(self, agreement):
        version = self._awaiting(agreement)
        return version.number if version else None

    def get_awaiting_my_signature(self, agreement) -> bool:
        version = self._awaiting(agreement)
        if version is None:
            return False
        party = party_of(self.context["request"].user, agreement.booking)
        return not any(s.party == party for s in version.signatures.all())


class ChallengeSerializer(serializers.Serializer):
    method = serializers.ChoiceField(
        choices=[("otp", "Re-confirm your phone by OTP"), ("none", "Consent only (tests)")]
    )
    consent_text = serializers.CharField()
    phone_hint = serializers.CharField(allow_blank=True)
    max_age_seconds = serializers.IntegerField()
    document_sha256 = serializers.CharField()


class SignSerializer(serializers.Serializer):
    consent = serializers.BooleanField(help_text="The signer ticked the consent statement.")
    document_sha256 = serializers.CharField(
        max_length=64, help_text="The fingerprint of the PDF the signer read."
    )
    otp_token = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="A fresh ID token from re-running phone OTP (method otp).",
    )


class ChangesSerializer(serializers.Serializer):
    """Send only the terms that should change."""

    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    hours_per_day = serializers.IntegerField(required=False)
    days_per_week = serializers.IntegerField(required=False)
    stay_type = serializers.CharField(required=False)
    meals = serializers.CharField(required=False)
    stipend_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    stipend_period = serializers.CharField(required=False, allow_blank=True)
    deliverables = TermsDeliverableSerializer(many=True, required=False)
    usage_rights = UsageRightsSerializer(required=False, allow_null=True)
    cancellation_policy = serializers.ChoiceField(
        choices=CancellationPolicy.choices, required=False
    )


class ProposeChangeSerializer(serializers.Serializer):
    changes = ChangesSerializer()
    reason = serializers.CharField(max_length=1000)


class DeclineChangeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PdfLinkSerializer(serializers.Serializer):
    url = serializers.URLField()
    expires_in = serializers.IntegerField(help_text="Seconds.")
    sha256 = serializers.CharField()
    size = serializers.IntegerField()
