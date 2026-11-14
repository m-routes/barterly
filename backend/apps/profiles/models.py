"""Role-specific profiles. A vendor has a VendorProfile; talent has a TalentProfile.

Profiles are saved field by field as the user fills them in, so most fields may be
blank; `missing_fields()` lists what still stops the profile counting as complete.
"""

import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.services.phone import normalize_phone
from apps.common.models import SoftDeleteModel, TimeStampedModel
from apps.profiles.constants import (
    LANGUAGES,
    MAX_LANGUAGES,
    MIN_AGE_YEARS,
    STATE_CHOICES,
    BusinessType,
    TalentType,
)

# 2 digits state code, 10-char PAN, entity number, 'Z', checksum character.
GSTIN_VALIDATOR = RegexValidator(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
    "Enter a valid 15-character GSTIN.",
)
INSTAGRAM_VALIDATOR = RegexValidator(
    r"^[A-Za-z0-9._]{1,30}$", "Enter an Instagram handle without the @."
)


def age_on(born: date, today: date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def validate_adult(born: date) -> None:
    """Talent must be 18 or older (ages counted on today's date in India)."""
    today = timezone.localdate()
    if born > today:
        raise ValidationError("Date of birth can't be in the future.", code="future")
    if age_on(born, today) < MIN_AGE_YEARS:
        raise ValidationError(
            f"You must be at least {MIN_AGE_YEARS} to join Barterly.", code="underage"
        )
    if age_on(born, today) > 100:
        raise ValidationError("Enter a real date of birth.", code="implausible")


def validate_languages(value) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationError("Send a list of language codes.", code="invalid")
    unknown = sorted(set(value) - set(LANGUAGES))
    if unknown:
        raise ValidationError(f"Unknown language codes: {', '.join(unknown)}.", code="unknown")
    if len(set(value)) != len(value):
        raise ValidationError("Each language once, please.", code="duplicate")
    if len(value) > MAX_LANGUAGES:
        raise ValidationError(f"At most {MAX_LANGUAGES} languages.", code="too_many")


def validate_phone(value: str) -> None:
    normalize_phone(value)  # raises ValidationError


class Skill(TimeStampedModel):
    """A skill talent can list. Curated by admins; talent pick from active ones."""

    name = models.CharField(max_length=60)
    slug = models.SlugField(max_length=60, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="profiles_skill_name_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.name


class BaseProfile(TimeStampedModel, SoftDeleteModel):
    required_role: str = ""
    # Fields that must be filled for the profile to be complete.
    completion_fields: tuple[str, ...] = ()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.user_id and self.user.role != self.required_role:
            raise ValidationError(
                {"user": f"Only users with the {self.required_role} role can have this profile."}
            )

    def missing_fields(self) -> list[str]:
        return [name for name in self.completion_fields if not self._is_filled(name)]

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields()

    def _is_filled(self, name: str) -> bool:
        value = getattr(self, name)
        if isinstance(value, str):
            return bool(value.strip())
        return value not in (None, [], {})


class TalentProfile(BaseProfile):
    required_role = Role.TALENT
    completion_fields = (
        "display_name",
        "bio",
        "talent_type",
        "skills",
        "languages",
        "home_city",
        "emergency_contact_name",
        "emergency_contact_phone",
        "date_of_birth",
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="talent_profile"
    )
    display_name = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True, max_length=2000)
    talent_type = models.CharField(max_length=20, choices=TalentType.choices, blank=True)
    skills = models.ManyToManyField(Skill, blank=True, related_name="talent_profiles")
    languages = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_languages],
        help_text='ISO 639 codes, e.g. ["en", "hi"]',
    )
    home_city = models.CharField(max_length=80, blank=True)
    emergency_contact_name = models.CharField(max_length=80, blank=True)
    emergency_contact_phone = models.CharField(
        max_length=16, blank=True, validators=[validate_phone], help_text="E.164"
    )
    date_of_birth = models.DateField(null=True, blank=True, validators=[validate_adult])
    instagram_handle = models.CharField(max_length=30, blank=True, validators=[INSTAGRAM_VALIDATOR])

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.display_name or f"Talent {self.user_id}"

    def clean(self):
        super().clean()
        if self.emergency_contact_phone:
            try:
                self.emergency_contact_phone = normalize_phone(self.emergency_contact_phone)
            except ValidationError as exc:
                raise ValidationError({"emergency_contact_phone": exc.messages}) from exc

    def _is_filled(self, name: str) -> bool:
        if name == "skills":
            return self.pk is not None and self.skills.exists()
        return super()._is_filled(name)


class VendorProfile(BaseProfile):
    required_role = Role.VENDOR
    completion_fields = ("business_name", "business_type", "contact_name", "city", "state", "about")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor_profile"
    )
    business_name = models.CharField(max_length=150, blank=True)
    business_type = models.CharField(max_length=20, choices=BusinessType.choices, blank=True)
    contact_name = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, choices=STATE_CHOICES, blank=True)
    about = models.TextField(blank=True, max_length=3000)
    address = models.TextField(blank=True, max_length=500)
    gstin = models.CharField(max_length=15, blank=True, validators=[GSTIN_VALIDATOR])
    website = models.URLField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.business_name or f"Vendor {self.user_id}"
