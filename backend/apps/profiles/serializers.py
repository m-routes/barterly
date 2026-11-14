from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.services.phone import normalize_phone
from apps.profiles.constants import LANGUAGES, MAX_LANGUAGES, MAX_SKILLS
from apps.profiles.models import INSTAGRAM_VALIDATOR, Skill, TalentProfile, VendorProfile


class UpperCaseCharField(serializers.CharField):
    def to_internal_value(self, data):
        return super().to_internal_value(data).upper()


class HandleField(serializers.CharField):
    """Accepts "@name" or "name"; stores "name"."""

    def to_internal_value(self, data):
        return super().to_internal_value(data).removeprefix("@")


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ["slug", "name"]


class _ProfileSerializer(serializers.ModelSerializer):
    profile_complete = serializers.SerializerMethodField()
    missing_fields = serializers.SerializerMethodField(
        help_text="Fields still empty that stop the profile counting as complete."
    )

    @extend_schema_field(serializers.BooleanField())
    def get_profile_complete(self, profile) -> bool:
        return profile.is_complete

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_missing_fields(self, profile) -> list[str]:
        return profile.missing_fields()


class VendorProfileSerializer(_ProfileSerializer):
    gstin = UpperCaseCharField(
        required=False, allow_blank=True, max_length=15, help_text="15-character GSTIN"
    )

    class Meta:
        model = VendorProfile
        fields = [
            "id",
            "business_name",
            "business_type",
            "contact_name",
            "city",
            "state",
            "about",
            "address",
            "gstin",
            "website",
            "profile_complete",
            "missing_fields",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_gstin(self, value: str) -> str:
        from apps.profiles.models import GSTIN_VALIDATOR

        if value:
            GSTIN_VALIDATOR(value)
        return value


class TalentProfileSerializer(_ProfileSerializer):
    skills = serializers.SlugRelatedField(
        many=True,
        slug_field="slug",
        queryset=Skill.objects.filter(is_active=True),
        required=False,
        help_text="Skill slugs from GET /api/v1/profiles/skills/.",
    )
    instagram_handle = HandleField(
        required=False,
        allow_blank=True,
        max_length=31,
        validators=[INSTAGRAM_VALIDATOR],
        help_text="With or without the @.",
    )
    languages = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(LANGUAGES.items())),
        max_length=MAX_LANGUAGES,
        required=False,
        help_text="ISO 639 codes, e.g. ['en', 'hi'].",
    )

    class Meta:
        model = TalentProfile
        fields = [
            "id",
            "display_name",
            "bio",
            "talent_type",
            "skills",
            "languages",
            "home_city",
            "emergency_contact_name",
            "emergency_contact_phone",
            "date_of_birth",
            "instagram_handle",
            "instagram_followers",
            "profile_complete",
            "missing_fields",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_skills(self, value):
        if len(value) > MAX_SKILLS:
            raise serializers.ValidationError(f"Pick at most {MAX_SKILLS} skills.")
        return list(dict.fromkeys(value))  # drop repeats, keep order

    def validate_languages(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Each language once, please.")
        return value

    def validate_emergency_contact_phone(self, value: str) -> str:
        return normalize_phone(value) if value else value

    def validate(self, attrs):
        phone = attrs.get("emergency_contact_phone")
        user = self.context["request"].user
        if phone and phone == user.phone:
            raise serializers.ValidationError(
                {"emergency_contact_phone": ["Use someone else's number, not your own."]}
            )
        return attrs
