from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import Role, User
from apps.accounts.services.auth import SELF_SERVICE_ROLES
from apps.privacy.models import CLIENT_SOURCES
from apps.profiles.services import is_profile_complete


class UserSerializer(serializers.ModelSerializer):
    # Declared so the schema says what the API sends: "" until a role is chosen.
    role = serializers.ChoiceField(
        choices=Role.choices,
        allow_blank=True,
        read_only=True,
        help_text='"" until the user picks vendor or talent at /api/v1/me/role/.',
    )
    profile_complete = serializers.SerializerMethodField(
        help_text="True once the user has a role and the matching profile."
    )
    needs_consent = serializers.SerializerMethodField(
        help_text=(
            "True when the terms or the privacy policy were never accepted, or changed "
            "since. Ask again (POST /api/v1/privacy/consents/) before going on."
        )
    )

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "email",
            "role",
            "is_active",
            "profile_complete",
            "needs_consent",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_profile_complete(self, user: User) -> bool:
        return is_profile_complete(user)

    @extend_schema_field(serializers.BooleanField())
    def get_needs_consent(self, user: User) -> bool:
        from apps.privacy.services.consents import needs_required_consent

        return needs_required_consent(user)


class ExchangeRequestSerializer(serializers.Serializer):
    id_token = serializers.CharField(
        max_length=8192,
        trim_whitespace=True,
        help_text="The ID token the client got from Firebase phone (OTP) sign-in.",
    )


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Short-lived JWT. Send as `Authorization: Bearer`.")
    refresh = serializers.CharField(help_text="Exchange at /api/v1/auth/refresh/ for new tokens.")


class ExchangeResponseSerializer(TokenPairSerializer):
    is_new_user = serializers.BooleanField()
    profile_complete = serializers.BooleanField()
    needs_role = serializers.BooleanField(
        help_text="True until the user picks vendor or talent at /api/v1/me/role/."
    )
    user = UserSerializer()


class RefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(max_length=4096)


class ChooseRoleSerializer(serializers.Serializer):
    """Sign-up's last step: the role, the 18+ declaration and the two required consents."""

    role = serializers.ChoiceField(choices=[(r.value, r.label) for r in SELF_SERVICE_ROLES])
    confirm_adult = serializers.BooleanField(
        help_text="The person declares they are 18 or older. Must be true."
    )
    terms_version = serializers.CharField(
        max_length=40, help_text="Version of the terms shown (GET /api/v1/privacy/documents/)."
    )
    privacy_version = serializers.CharField(
        max_length=40, help_text="Version of the privacy policy shown."
    )
    source = serializers.ChoiceField(choices=CLIENT_SOURCES, default="api")
    invite_code = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        help_text=(
            "During the closed beta: the invite code (GET /api/v1/beta/ says which roles "
            "need one). With or without the dash, any case."
        ),
    )

    def validate_confirm_adult(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                "You must be 18 or older to use Barterly.", code="underage"
            )
        return value
