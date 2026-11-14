from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.discovery.filters import DiscoveryQuerySerializer, to_storable
from apps.discovery.models import MAX_SAVED_SEARCHES, SavedSearch
from apps.gigs.models import Gig
from apps.media.services.uploads import read_urls
from apps.properties.models import PUBLIC_RADIUS_M
from apps.verification.constants import CaseStatus


class ComponentSerializer(serializers.Serializer):
    value = serializers.FloatField(help_text="0 to 1.")
    weight = serializers.FloatField()
    points = serializers.FloatField(help_text="What this component adds to the score.")
    neutral = serializers.BooleanField(help_text="No data yet, so the neutral value was used.")
    reason = serializers.CharField()


class FitSerializer(serializers.Serializer):
    score = serializers.IntegerField(help_text="0 to 100.")
    breakdown = serializers.DictField(child=ComponentSerializer())


class GigPropertySummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    property_type = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    women_friendly = serializers.BooleanField()
    verified = serializers.BooleanField()
    approximate_location = serializers.DictField(allow_null=True)
    cover_thumb_url = serializers.URLField(allow_null=True)


class GigCardSerializer(serializers.ModelSerializer):
    property = serializers.SerializerMethodField()
    host_verified = serializers.SerializerMethodField(
        help_text="The property is verified and the host's ID is verified."
    )
    skills = serializers.SlugRelatedField(many=True, read_only=True, slug_field="slug")
    distance_km = serializers.SerializerMethodField()
    fit = serializers.SerializerMethodField()

    class Meta:
        model = Gig
        fields = [
            "id",
            "title",
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
            "skills",
            "languages",
            "min_followers",
            "min_stay_days",
            "required_verification",
            "published_at",
            "property",
            "host_verified",
            "distance_km",
            "fit",
        ]
        read_only_fields = fields

    def _scored(self, gig):
        return self.context["scored"][gig.pk]

    @extend_schema_field(GigPropertySummarySerializer)
    def get_property(self, gig):
        prop = gig.property
        photos = list(prop.photos.all())
        cover = read_urls(photos[0].media) if photos else None
        return {
            "id": prop.pk,
            "name": prop.name,
            "property_type": prop.property_type,
            "city": prop.city,
            "state": prop.state,
            "women_friendly": prop.women_friendly,
            "verified": prop.verification_status == CaseStatus.APPROVED,
            "approximate_location": None
            if prop.approx_latitude is None
            else {
                "latitude": float(prop.approx_latitude),
                "longitude": float(prop.approx_longitude),
                "radius_m": PUBLIC_RADIUS_M,
            },
            "cover_thumb_url": (cover["variants"].get("thumb") or cover["url"]) if cover else None,
        }

    @extend_schema_field(serializers.BooleanField())
    def get_host_verified(self, gig) -> bool:
        return gig.property.verification_status == CaseStatus.APPROVED and bool(
            getattr(gig, "vendor_id_verified", False)
        )

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_distance_km(self, gig):
        distance = self._scored(gig).distance_km
        return None if distance is None else round(distance, 1)

    @extend_schema_field(FitSerializer)
    def get_fit(self, gig):
        fit = self._scored(gig).fit
        return {"score": fit.score, "breakdown": fit.breakdown()}


class GigPageSerializer(serializers.Serializer):
    results = GigCardSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    next = serializers.URLField(allow_null=True)


class SavedSearchSerializer(serializers.ModelSerializer):
    params = serializers.JSONField(help_text="The same filters as GET /api/v1/gigs/.")

    class Meta:
        model = SavedSearch
        fields = ["id", "name", "params", "alerts_enabled", "last_checked_at", "created_at"]
        read_only_fields = ["id", "last_checked_at", "created_at"]

    def validate_params(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Send the filters as an object.")
        query = DiscoveryQuerySerializer(data=value)
        query.is_valid(raise_exception=True)
        return to_storable(query.validated_data)

    def validate(self, attrs):
        request = self.context["request"]
        if self.instance is None and (
            SavedSearch.objects.filter(talent=request.user).count() >= MAX_SAVED_SEARCHES
        ):
            raise serializers.ValidationError(f"At most {MAX_SAVED_SEARCHES} saved searches.")
        return attrs
