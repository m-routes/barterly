"""Role-specific profiles. A vendor has a VendorProfile; talent has a TalentProfile."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.accounts.models import Role
from apps.common.models import SoftDeleteModel, TimeStampedModel

# 2 digits state code, 10-char PAN, entity number, 'Z', checksum character.
GSTIN_VALIDATOR = RegexValidator(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
    "Enter a valid 15-character GSTIN.",
)


class BaseProfile(TimeStampedModel, SoftDeleteModel):
    required_role: str = ""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.user_id and self.user.role != self.required_role:
            raise ValidationError(
                {"user": f"Only users with the {self.required_role} role can have this profile."}
            )


class TalentProfile(BaseProfile):
    required_role = Role.TALENT

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="talent_profile"
    )
    full_name = models.CharField(max_length=120)
    bio = models.TextField(blank=True, max_length=2000)
    home_city = models.CharField(max_length=80, blank=True)
    languages = models.JSONField(default=list, blank=True, help_text='e.g. ["English", "Hindi"]')
    skills = models.JSONField(
        default=list, blank=True, help_text='e.g. ["front desk", "photography"]'
    )
    instagram_handle = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.full_name


class PropertyType(models.TextChoices):
    HOSTEL = "hostel", "Hostel"
    HOMESTAY = "homestay", "Homestay"
    GUESTHOUSE = "guesthouse", "Guesthouse"
    HOTEL = "hotel", "Hotel"
    CAFE = "cafe", "Café"
    CAMP = "camp", "Camp"
    OTHER = "other", "Other"


class VendorProfile(BaseProfile):
    required_role = Role.VENDOR

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor_profile"
    )
    business_name = models.CharField(max_length=150)
    property_type = models.CharField(max_length=20, choices=PropertyType.choices)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[GSTIN_VALIDATOR])
    website = models.URLField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.business_name
