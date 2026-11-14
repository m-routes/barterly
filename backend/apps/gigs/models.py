"""Gigs: what a vendor offers, for whom, and what they give in return.

Business rules live in apps.gigs.rules and run in the service layer on every submit
and every edit of a gig past draft. The constraints below are a backstop for the few
rules that hold for every row, drafts included. The minimum age (18) is fixed for
every gig, so it is a constant (apps.gigs.constants.MIN_AGE_YEARS), not a column.
"""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel
from apps.gigs.constants import (
    MAX_DAYS_PER_WEEK,
    MAX_HOURS_PER_DAY,
    CompensationModel,
    GigStatus,
    Meals,
    RoleTemplate,
    StayType,
    StipendPeriod,
)


class Gig(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="gigs"
    )
    property = models.ForeignKey(
        "properties.Property", on_delete=models.PROTECT, related_name="gigs"
    )
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=5000, blank=True)
    role_template = models.CharField(max_length=20, choices=RoleTemplate.choices)
    compensation_model = models.CharField(max_length=20, choices=CompensationModel.choices)

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    duration_days = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Instead of an end date, for flexible starts."
    )
    apply_by = models.DateField(null=True, blank=True)
    slots = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])

    hours_per_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_HOURS_PER_DAY)],
    )
    days_per_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_DAYS_PER_WEEK)],
        help_text="At most 6: everyone gets at least one day off.",
    )
    stay_type = models.CharField(max_length=20, choices=StayType.choices, blank=True)
    meals = models.CharField(max_length=20, choices=Meals.choices, blank=True)
    wifi = models.BooleanField(default=False)

    stipend_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="INR. Hybrid and paid only.",
    )
    stipend_period = models.CharField(max_length=10, choices=StipendPeriod.choices, blank=True)
    deliverables = models.JSONField(
        default=list,
        blank=True,
        help_text='Barter and hybrid only, e.g. [{"type": "instagram_reel", "quantity": 2}]',
    )

    languages = models.JSONField(default=list, blank=True, help_text="ISO 639 codes.")
    min_followers = models.PositiveIntegerField(null=True, blank=True)
    min_stay_days = models.PositiveSmallIntegerField(null=True, blank=True)
    screening_questions = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=20, choices=GigStatus.choices, default=GigStatus.DRAFT)
    status_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Why it was sent back or reopened. Shown to the vendor.",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "apply_by"], name="gig_status_apply_by_idx"),
            models.Index(fields=["vendor", "status"], name="gig_vendor_status_idx"),
            models.Index(fields=["property", "status"], name="gig_property_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(slots__gte=1), name="gig_slots_at_least_one"),
            models.CheckConstraint(
                condition=Q(hours_per_day__isnull=True)
                | Q(hours_per_day__gte=1, hours_per_day__lte=MAX_HOURS_PER_DAY),
                name="gig_hours_per_day_max_6",
            ),
            models.CheckConstraint(
                condition=Q(days_per_week__isnull=True)
                | Q(days_per_week__gte=1, days_per_week__lte=MAX_DAYS_PER_WEEK),
                name="gig_one_day_off",
            ),
            models.CheckConstraint(
                condition=Q(stipend_amount__isnull=True) | Q(stipend_amount__gt=0),
                name="gig_stipend_positive",
            ),
            models.CheckConstraint(
                condition=Q(status__in=GigStatus.values), name="gig_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return self.title
