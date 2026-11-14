from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.media.services.uploads import read_urls
from apps.properties.models import (
    AMENITIES,
    MAX_HOUSE_RULES,
    PUBLIC_RADIUS_M,
    Property,
    PropertyPhoto,
)
from apps.properties.services import can_see_exact_location


def _photo_urls(serializer, media) -> dict:
    cache = serializer.context.setdefault("_urls", {})
    if media.pk not in cache:
        cache[media.pk] = read_urls(media)
    return cache[media.pk]


class PhotoSerializer(serializers.ModelSerializer):
    media_id = serializers.UUIDField(source="media.pk", read_only=True)
    status = serializers.CharField(source="media.status", read_only=True)
    url = serializers.SerializerMethodField(help_text="Signed, short-lived; null until ready.")
    thumb_url = serializers.SerializerMethodField()

    class Meta:
        model = PropertyPhoto
        fields = [
            "id",
            "media_id",
            "status",
            "position",
            "caption",
            "latitude",
            "longitude",
            "captured_at",
            "url",
            "thumb_url",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_url(self, photo):
        urls = _photo_urls(self, photo.media)
        return urls["variants"].get("medium") or urls["url"]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_thumb_url(self, photo):
        return _photo_urls(self, photo.media)["variants"].get("thumb")


class AddPhotoSerializer(serializers.Serializer):
    media_id = serializers.UUIDField(help_text="A confirmed upload of kind 'photo'.")
    caption = serializers.CharField(max_length=200, required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90, required=False
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180, required=False
    )
    captured_at = serializers.DateTimeField(required=False)


class PropertySerializer(serializers.ModelSerializer):
    """The owner's view: everything, including the exact address and pin."""

    amenities = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(AMENITIES.items())),
        required=False,
        help_text="Amenity codes.",
    )
    house_rules = serializers.ListField(
        child=serializers.CharField(max_length=200),
        max_length=MAX_HOUSE_RULES,
        required=False,
    )
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=-180,
        max_value=180,
        required=False,
        allow_null=True,
    )
    photos = PhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "property_type",
            "address",
            "city",
            "state",
            "pincode",
            "latitude",
            "longitude",
            "location_confirmed",
            "amenities",
            "house_rules",
            "women_friendly",
            "verification_status",
            "photos",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "verification_status", "photos", "created_at", "updated_at"]
        extra_kwargs = {
            "location_confirmed": {
                "help_text": "Send true once the vendor has checked the pin. Moving the pin or "
                "changing the address resets it unless sent again."
            }
        }

    def validate_amenities(self, value):
        return list(dict.fromkeys(value))

    def validate_house_rules(self, value):
        return [rule.strip() for rule in value]


class ApproximateLocationSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    radius_m = serializers.IntegerField(help_text="The property is within this distance.")


class ExactLocationSerializer(serializers.Serializer):
    address = serializers.CharField()
    pincode = serializers.CharField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)


class PublicPhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()

    class Meta:
        model = PropertyPhoto
        fields = ["id", "caption", "url", "thumb_url"]
        read_only_fields = fields

    @extend_schema_field(serializers.URLField())
    def get_url(self, photo):
        urls = _photo_urls(self, photo.media)
        return urls["variants"].get("medium") or urls["url"]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_thumb_url(self, photo):
        return _photo_urls(self, photo.media)["variants"].get("thumb")


class PublicPropertySerializer(serializers.ModelSerializer):
    """What anyone may see. No street address or exact point unless allowed."""

    verified = serializers.SerializerMethodField()
    approximate_location = serializers.SerializerMethodField()
    exact_location = serializers.SerializerMethodField(
        help_text="Only for the owner, admins, and (once bookings exist) confirmed guests."
    )
    photos = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "property_type",
            "city",
            "state",
            "amenities",
            "house_rules",
            "women_friendly",
            "verified",
            "approximate_location",
            "exact_location",
            "photos",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_verified(self, prop) -> bool:
        return prop.verification_status == "approved"

    @extend_schema_field(ApproximateLocationSerializer(allow_null=True))
    def get_approximate_location(self, prop):
        if prop.approx_latitude is None:
            return None
        return {
            "latitude": float(prop.approx_latitude),
            "longitude": float(prop.approx_longitude),
            "radius_m": PUBLIC_RADIUS_M,
        }

    @extend_schema_field(ExactLocationSerializer(allow_null=True))
    def get_exact_location(self, prop):
        if not can_see_exact_location(self.context["request"].user, prop):
            return None
        return {
            "address": prop.address,
            "pincode": prop.pincode,
            "latitude": float(prop.latitude) if prop.has_point else None,
            "longitude": float(prop.longitude) if prop.has_point else None,
        }

    @extend_schema_field(PublicPhotoSerializer(many=True))
    def get_photos(self, prop):
        servable = [p for p in prop.photos.all() if _photo_urls(self, p.media)["url"]]
        return PublicPhotoSerializer(servable, many=True, context=self.context).data
