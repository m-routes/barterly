"""Vendor properties with their location and photos.

Location is plain latitude/longitude columns (Cloud SQL without PostGIS/GDAL):
`Property.objects.within_radius()` filters on an indexed bounding box, then on the exact
haversine distance computed in SQL.

The public sees only `approx_latitude/approx_longitude`: the real point moved a fixed,
secret-seeded 300-900 m, so repeated requests can't be averaged back to the real spot.
"""

import hashlib
import hmac
import math
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, FloatField, Q
from django.db.models.functions import ASin, Cast, Cos, Power, Radians, Sin, Sqrt

from apps.common.models import SoftDeleteQuerySet, TimeStampedModel
from apps.geo.distance import EARTH_RADIUS_M, bounding_box, offset
from apps.profiles.constants import STATE_CHOICES
from apps.verification.constants import CaseStatus

APPROX_MIN_M, APPROX_MAX_M = 300, 900
PUBLIC_RADIUS_M = 1000
MAX_PHOTOS = 20
MAX_HOUSE_RULES = 20
PINCODE_VALIDATOR = RegexValidator(r"^[1-9][0-9]{5}$", "Enter a 6-digit PIN code.")


class PropertyType(models.TextChoices):
    HOSTEL = "hostel", "Hostel"
    HOMESTAY = "homestay", "Homestay"
    CAFE = "cafe", "Café"
    HOTEL = "hotel", "Hotel"
    TREK_OPERATOR = "trek_operator", "Trek operator"


AMENITIES = {
    "wifi": "Wi-Fi", "hot_water": "Hot water", "kitchen": "Shared kitchen",
    "laundry": "Laundry", "parking": "Parking", "air_conditioning": "Air conditioning",
    "power_backup": "Power backup", "workspace": "Workspace", "common_area": "Common area",
    "lockers": "Lockers", "breakfast": "Breakfast", "pet_friendly": "Pet friendly",
    "female_dorm": "Female-only dorm", "first_aid": "First aid", "cctv": "CCTV in common areas",
}  # fmt: skip


def validate_amenities(value) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationError("Send a list of amenity codes.", code="invalid")
    unknown = sorted(set(value) - set(AMENITIES))
    if unknown:
        raise ValidationError(f"Unknown amenities: {', '.join(unknown)}.", code="unknown")


def validate_house_rules(value) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ValidationError("Send a list of rules as text.", code="invalid")
    if len(value) > MAX_HOUSE_RULES:
        raise ValidationError(f"At most {MAX_HOUSE_RULES} rules.", code="too_many")
    if any(len(v) > 200 for v in value):
        raise ValidationError("Keep each rule under 200 characters.", code="too_long")


class PropertyQuerySet(SoftDeleteQuerySet):
    def within_radius(self, latitude: float, longitude: float, radius_m: float, *, public=True):
        """Properties within radius_m, nearest first, annotated with `distance_m`.

        public=True measures from the approximate point, which is all anyone but the
        owner may see; ordering by the real point would leak it.
        """
        lat_f, lng_f = (
            ("approx_latitude", "approx_longitude") if public else ("latitude", "longitude")
        )
        box = bounding_box(latitude, longitude, radius_m)
        lat = Radians(Cast(F(lat_f), FloatField()))
        lng = Radians(Cast(F(lng_f), FloatField()))
        lat0, lng0 = math.radians(latitude), math.radians(longitude)
        a = Power(Sin((lat - lat0) / 2), 2) + math.cos(lat0) * Cos(lat) * Power(
            Sin((lng - lng0) / 2), 2
        )
        distance = 2 * EARTH_RADIUS_M * ASin(Sqrt(a))
        return (
            self.filter(
                **{
                    f"{lat_f}__gte": box.min_lat,
                    f"{lat_f}__lte": box.max_lat,
                    f"{lng_f}__gte": box.min_lng,
                    f"{lng_f}__lte": box.max_lng,
                }
            )
            .annotate(distance_m=distance)
            .filter(distance_m__lte=radius_m)
            .order_by("distance_m")
        )


class PropertyManager(models.Manager.from_queryset(PropertyQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Property(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="properties"
    )
    name = models.CharField(max_length=150)
    property_type = models.CharField(max_length=20, choices=PropertyType.choices)
    address = models.TextField(max_length=500, help_text="Street address. Never shown publicly.")
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80, choices=STATE_CHOICES)
    pincode = models.CharField(max_length=6, blank=True, validators=[PINCODE_VALIDATOR])
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_confirmed = models.BooleanField(
        default=False, help_text="The vendor confirmed the pin marks the property."
    )
    approx_latitude = models.DecimalField(
        max_digits=9, decimal_places=4, null=True, blank=True, editable=False
    )
    approx_longitude = models.DecimalField(
        max_digits=9, decimal_places=4, null=True, blank=True, editable=False
    )
    amenities = models.JSONField(default=list, blank=True, validators=[validate_amenities])
    house_rules = models.JSONField(default=list, blank=True, validators=[validate_house_rules])
    women_friendly = models.BooleanField(
        default=False, help_text="Vendor's claim: female staff or dorms, safe for solo women."
    )
    verification_status = models.CharField(
        max_length=20,
        choices=CaseStatus.choices,
        default=CaseStatus.NOT_STARTED,
        editable=False,
        help_text="Mirrors the property's verification case.",
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)

    objects = PropertyManager()
    all_objects = models.Manager.from_queryset(PropertyQuerySet)()

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "properties"
        indexes = [
            models.Index(fields=["latitude", "longitude"], name="property_point_idx"),
            models.Index(
                fields=["approx_latitude", "approx_longitude"], name="property_approx_idx"
            ),
            models.Index(fields=["vendor", "deleted_at"], name="property_vendor_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__isnull=True, longitude__isnull=True)
                | Q(
                    latitude__isnull=False,
                    longitude__isnull=False,
                    latitude__gte=-90,
                    latitude__lte=90,
                    longitude__gte=-180,
                    longitude__lte=180,
                ),
                name="property_point_complete_and_valid",
            ),
            models.CheckConstraint(
                condition=Q(location_confirmed=False) | Q(latitude__isnull=False),
                name="property_confirmed_needs_point",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def has_point(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def save(self, *args, **kwargs):
        self.approx_latitude, self.approx_longitude = approximate_point(self)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {
                *kwargs["update_fields"],
                "approx_latitude",
                "approx_longitude",
            }
        super().save(*args, **kwargs)


def approximate_point(prop: Property) -> tuple[Decimal | None, Decimal | None]:
    """A fixed point 300-900 m from the real one, in a direction seeded by a secret."""
    if not prop.has_point:
        return None, None
    seed = hmac.new(
        settings.SECRET_KEY.encode(), f"property-approx:{prop.pk}".encode(), hashlib.sha256
    ).digest()
    angle = int.from_bytes(seed[:4], "big") / 2**32 * 2 * math.pi
    distance = APPROX_MIN_M + int.from_bytes(seed[4:8], "big") / 2**32 * (
        APPROX_MAX_M - APPROX_MIN_M
    )
    lat, lng = offset(
        float(prop.latitude),
        float(prop.longitude),
        north_m=distance * math.cos(angle),
        east_m=distance * math.sin(angle),
    )
    return Decimal(f"{lat:.4f}"), Decimal(f"{lng:.4f}")


class PropertyPhoto(TimeStampedModel):
    """A photo of the property: one of the vendor's uploads, with where it was taken."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photos")
    media = models.ForeignKey(
        "media.MediaFile", on_delete=models.PROTECT, related_name="property_photos"
    )
    position = models.PositiveSmallIntegerField(default=0)
    caption = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, help_text="From EXIF or the device."
    )
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["property", "media"], name="property_photo_once"),
            models.CheckConstraint(
                condition=Q(latitude__isnull=True, longitude__isnull=True)
                | Q(latitude__isnull=False, longitude__isnull=False),
                name="property_photo_point_complete",
            ),
        ]

    def __str__(self) -> str:
        return f"Photo {self.position} of {self.property_id}"
