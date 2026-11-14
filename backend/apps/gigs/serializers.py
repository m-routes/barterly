from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.gigs.constants import (
    MAX_DELIVERABLES,
    MAX_SCREENING_QUESTIONS,
    MIN_AGE_YEARS,
    DeliverableType,
    GigStatus,
)
from apps.gigs.models import Gig
from apps.profiles.constants import LANGUAGES
from apps.properties.models import Property


class DeliverableSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=DeliverableType.choices)
    quantity = serializers.IntegerField(min_value=1, max_value=50)
    notes = serializers.CharField(max_length=300, required=False, allow_blank=True)


class GigSerializer(serializers.ModelSerializer):
    property = serializers.PrimaryKeyRelatedField(queryset=Property.objects.none())
    deliverables = DeliverableSerializer(many=True, required=False, max_length=MAX_DELIVERABLES)
    languages = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(LANGUAGES.items())), required=False
    )
    screening_questions = serializers.ListField(
        child=serializers.CharField(max_length=300),
        max_length=MAX_SCREENING_QUESTIONS,
        required=False,
    )
    min_age = serializers.SerializerMethodField(help_text="Fixed at 18 for every gig.")

    class Meta:
        model = Gig
        fields = [
            "id",
            "property",
            "title",
            "description",
            "role_template",
            "compensation_model",
            "start_date",
            "end_date",
            "duration_days",
            "apply_by",
            "slots",
            "hours_per_day",
            "days_per_week",
            "stay_type",
            "meals",
            "wifi",
            "stipend_amount",
            "stipend_period",
            "deliverables",
            "min_age",
            "languages",
            "min_followers",
            "min_stay_days",
            "screening_questions",
            "status",
            "status_reason",
            "submitted_at",
            "published_at",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "status_reason",
            "submitted_at",
            "published_at",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "hours_per_day": {"help_text": "1 to 6."},
            "days_per_week": {"help_text": "1 to 6: at least one day off."},
            "stipend_amount": {"help_text": "INR, above zero. Hybrid and paid only."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            self.fields["property"].queryset = Property.objects.filter(vendor=request.user)

    @extend_schema_field(serializers.IntegerField())
    def get_min_age(self, gig) -> int:
        return MIN_AGE_YEARS

    def validate_deliverables(self, value):
        return [{k: v for k, v in dict(item).items() if v != ""} for item in value]

    def validate_screening_questions(self, value):
        return [q.strip() for q in value]


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=GigStatus.choices)
    reason = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Required when an admin sends a gig back. Shown to the vendor.",
    )
