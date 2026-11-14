"""The discovery query: what talent can filter and sort by. Saved searches store it."""

from rest_framework import serializers

from apps.gigs.constants import CompensationModel, RoleTemplate, StayType


class Sort:
    BEST_FIT = "best_fit"
    NEWEST = "newest"
    START_DATE = "start_date"
    DISTANCE = "distance"
    CHOICES = (BEST_FIT, NEWEST, START_DATE, DISTANCE)


class CommaChoiceField(serializers.ListField):
    """Accepts ?x=a,b or ?x=a&x=b (and a JSON list in saved searches)."""

    def __init__(self, choices, **kwargs):
        super().__init__(child=serializers.ChoiceField(choices=choices), **kwargs)

    def get_value(self, dictionary):
        if hasattr(dictionary, "getlist"):
            raw = dictionary.getlist(self.field_name)
            if not raw:
                return serializers.empty
            return [part for item in raw for part in item.split(",") if part]
        return super().get_value(dictionary)


class DiscoveryQuerySerializer(serializers.Serializer):
    compensation_model = CommaChoiceField(CompensationModel.choices, required=False)
    role = CommaChoiceField(RoleTemplate.choices, required=False)
    stay_type = CommaChoiceField(StayType.choices, required=False)
    city = serializers.CharField(max_length=80, required=False)
    latitude = serializers.FloatField(min_value=-90, max_value=90, required=False)
    longitude = serializers.FloatField(min_value=-180, max_value=180, required=False)
    radius_km = serializers.FloatField(min_value=1, max_value=1000, required=False)
    start_from = serializers.DateField(required=False, help_text="Gigs starting on or after.")
    start_to = serializers.DateField(required=False, help_text="Gigs starting on or before.")
    women_friendly = serializers.BooleanField(required=False, default=None, allow_null=True)
    verified_hosts = serializers.BooleanField(required=False, default=None, allow_null=True)
    min_stay = serializers.IntegerField(
        min_value=1,
        max_value=365,
        required=False,
        help_text="How many days you can stay: hides gigs that need a longer minimum stay.",
    )
    q = serializers.CharField(max_length=200, required=False, help_text="Keywords.")
    sort = serializers.ChoiceField(choices=Sort.CHOICES, default=Sort.BEST_FIT)

    def validate(self, attrs):
        has_lat, has_lng = "latitude" in attrs, "longitude" in attrs
        if has_lat != has_lng:
            raise serializers.ValidationError(
                {"latitude": ["Send latitude and longitude together."]}
            )
        if "radius_km" in attrs and not has_lat:
            raise serializers.ValidationError({"radius_km": ["A radius needs a point."]})
        if attrs.get("sort") == Sort.DISTANCE and not has_lat:
            raise serializers.ValidationError({"sort": ["Sorting by distance needs a point."]})
        if (
            attrs.get("start_from")
            and attrs.get("start_to")
            and attrs["start_from"] > attrs["start_to"]
        ):
            raise serializers.ValidationError({"start_to": ["Must be on or after start_from."]})
        return {k: v for k, v in attrs.items() if v is not None}


def to_storable(params: dict) -> dict:
    """JSON-safe form of validated params (dates as ISO strings) for saved searches."""
    return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in params.items()}
