from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.services.auth import SELF_SERVICE_ROLES
from apps.profiles.services import is_profile_complete


class UserSerializer(serializers.ModelSerializer):
    profile_complete = serializers.SerializerMethodField(
        help_text="True once the user has a role and the matching profile."
    )

    class Meta:
        model = User
        fields = ["id", "phone", "email", "role", "is_active", "profile_complete", "created_at"]
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_profile_complete(self, user: User) -> bool:
        return is_profile_complete(user)


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
    refresh = serializers.CharField()


class ChooseRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[(r.value, r.label) for r in SELF_SERVICE_ROLES])
