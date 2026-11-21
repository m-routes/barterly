"""The terms of an offer, frozen as a snapshot.

An offer's terms are a plain JSON object (see TermsSerializer for the fields). Once an
offer is sent its terms never change: a counter or a later change to the agreement is a
new snapshot. canonical() gives the one serialisation that is hashed and stored, so the
same terms always hash the same.

The talent may counter only the fields in COUNTERABLE; the stay, meals, how the gig is
paid and the cancellation policy are the vendor's to set.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import models
from django.utils import timezone
from rest_framework import serializers

from apps.gigs.constants import (
    DELIVERABLE_MODELS,
    MAX_DAYS_PER_WEEK,
    MAX_DELIVERABLES,
    MAX_HOURS_PER_DAY,
    STIPEND_MODELS,
    CompensationModel,
    DeliverableType,
    Meals,
    StayType,
    StipendPeriod,
)

MAX_TERM_DAYS = 365
MAX_USAGE_MONTHS = 36


class UsageScope(models.TextChoices):
    ORGANIC = "organic", "The host's own social channels and website"
    ORGANIC_AND_ADS = "organic_and_ads", "Own channels, website and paid ads"


class CancellationPolicy(models.TextChoices):
    FLEXIBLE = "flexible", "Flexible"
    MODERATE = "moderate", "Moderate"
    STRICT = "strict", "Strict"


# Days before the start by which either side may cancel without it counting against them.
CANCELLATION_NOTICE_DAYS = {
    CancellationPolicy.FLEXIBLE: 3,
    CancellationPolicy.MODERATE: 7,
    CancellationPolicy.STRICT: 14,
}

# Fields the talent may change in their one counter.
COUNTERABLE = (
    "start_date",
    "end_date",
    "hours_per_day",
    "days_per_week",
    "stipend_amount",
    "deliverables",
    "usage_rights",
)
# Fields that can't change once the stay has begun.
DATE_FIELDS = ("start_date", "end_date")


class TermsDeliverableSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=DeliverableType.choices)
    quantity = serializers.IntegerField(min_value=1, max_value=50)
    notes = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class UsageRightsSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=UsageScope.choices)
    duration_months = serializers.IntegerField(min_value=1, max_value=MAX_USAGE_MONTHS)
    credit_required = serializers.BooleanField(
        help_text="The host credits the talent (name or handle) when using the content."
    )


class TermsSerializer(serializers.Serializer):
    """Everything both sides agree to. Validated against the gig's pay model."""

    compensation_model = serializers.ChoiceField(choices=CompensationModel.choices, read_only=True)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    hours_per_day = serializers.IntegerField(min_value=1, max_value=MAX_HOURS_PER_DAY)
    days_per_week = serializers.IntegerField(
        min_value=1,
        max_value=MAX_DAYS_PER_WEEK,
        help_text="At most 6: everyone gets at least one day off.",
    )
    stay_type = serializers.ChoiceField(choices=StayType.choices)
    meals = serializers.ChoiceField(choices=Meals.choices)
    stipend_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("1"),
        allow_null=True,
        required=False,
        default=None,
        help_text="INR. Hybrid and paid gigs only.",
    )
    stipend_period = serializers.ChoiceField(
        choices=StipendPeriod.choices, allow_blank=True, required=False, default=""
    )
    deliverables = TermsDeliverableSerializer(
        many=True, required=False, default=list, max_length=MAX_DELIVERABLES
    )
    usage_rights = UsageRightsSerializer(
        allow_null=True,
        required=False,
        default=None,
        help_text="How the host may use the talent's content. Barter and hybrid gigs only.",
    )
    cancellation_policy = serializers.ChoiceField(choices=CancellationPolicy.choices)

    def __init__(self, *args, compensation_model: str = "", today: date | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.compensation_model = compensation_model
        self.today = today or timezone.localdate()

    def validate(self, attrs):
        model = self.compensation_model
        if not model:
            raise serializers.ValidationError("Terms are checked against the gig's pay model.")
        errors: dict[str, str] = {}
        if attrs["end_date"] <= attrs["start_date"]:
            errors["end_date"] = "The end date must be after the start date."
        elif (attrs["end_date"] - attrs["start_date"]).days > MAX_TERM_DAYS:
            errors["end_date"] = f"At most {MAX_TERM_DAYS} days."
        if attrs["start_date"] < self.today:
            errors["start_date"] = "The start date can't be in the past."
        if model in STIPEND_MODELS:
            if attrs.get("stipend_amount") is None:
                errors["stipend_amount"] = "Give the stipend."
            if not attrs.get("stipend_period"):
                errors["stipend_period"] = "Say what the stipend covers."
        else:
            if attrs.get("stipend_amount") is not None:
                errors["stipend_amount"] = "Only hybrid and paid gigs have a stipend."
            attrs["stipend_period"] = ""
        if model in DELIVERABLE_MODELS:
            if not attrs.get("deliverables"):
                errors["deliverables"] = "List what the talent will create."
            elif len(attrs["deliverables"]) > MAX_DELIVERABLES:
                errors["deliverables"] = f"At most {MAX_DELIVERABLES} deliverables."
            if attrs.get("usage_rights") is None:
                errors["usage_rights"] = "Say how you may use the content."
        else:
            if attrs.get("deliverables"):
                errors["deliverables"] = "Only barter and hybrid gigs ask for deliverables."
            if attrs.get("usage_rights") is not None:
                errors["usage_rights"] = "Only barter and hybrid gigs have content to use."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def canonical(terms: dict[str, Any]) -> dict[str, Any]:
    """The stored form: JSON types only, every field present, in a fixed shape."""
    stipend = terms.get("stipend_amount")
    usage = terms.get("usage_rights")
    return {
        "compensation_model": str(terms["compensation_model"]),
        "start_date": str(terms["start_date"]),
        "end_date": str(terms["end_date"]),
        "hours_per_day": int(terms["hours_per_day"]),
        "days_per_week": int(terms["days_per_week"]),
        "stay_type": str(terms["stay_type"]),
        "meals": str(terms["meals"]),
        "stipend_amount": None if stipend is None else f"{Decimal(str(stipend)):.2f}",
        "stipend_period": str(terms.get("stipend_period") or ""),
        "deliverables": [
            {
                "type": str(d["type"]),
                "quantity": int(d["quantity"]),
                "notes": str(d.get("notes") or ""),
            }
            for d in terms.get("deliverables") or []
        ],
        "usage_rights": None
        if usage is None
        else {
            "scope": str(usage["scope"]),
            "duration_months": int(usage["duration_months"]),
            "credit_required": bool(usage["credit_required"]),
        },
        "cancellation_policy": str(terms["cancellation_policy"]),
    }


def digest(terms: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON: equal terms, equal hash."""
    data = json.dumps(canonical(terms), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def validate(
    data: dict[str, Any], *, compensation_model: str, today: date | None = None
) -> dict[str, Any]:
    """Validate submitted terms for a gig with this pay model; return the canonical form.
    Raises rest_framework.serializers.ValidationError."""
    serializer = TermsSerializer(data=data, compensation_model=compensation_model, today=today)
    serializer.is_valid(raise_exception=True)
    return canonical({**serializer.validated_data, "compensation_model": compensation_model})


def changed_fields(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    a, b = canonical(old), canonical(new)
    return [name for name in a if a[name] != b[name]]


def draft_for(application) -> dict[str, Any]:
    """Terms to start an offer from: the gig's, with the talent's dates."""
    gig = application.gig
    model = gig.compensation_model
    with_content = model in DELIVERABLE_MODELS
    return canonical(
        {
            "compensation_model": model,
            "start_date": application.proposed_start,
            "end_date": application.proposed_end,
            "hours_per_day": gig.hours_per_day or MAX_HOURS_PER_DAY,
            "days_per_week": gig.days_per_week or 5,
            "stay_type": gig.stay_type or StayType.NONE,
            "meals": gig.meals or Meals.NONE,
            "stipend_amount": gig.stipend_amount if model in STIPEND_MODELS else None,
            "stipend_period": gig.stipend_period if model in STIPEND_MODELS else "",
            "deliverables": gig.deliverables if with_content else [],
            "usage_rights": {
                "scope": UsageScope.ORGANIC,
                "duration_months": 12,
                "credit_required": True,
            }
            if with_content
            else None,
            "cancellation_policy": CancellationPolicy.MODERATE,
        }
    )


def weekly_hour_cap(terms: dict[str, Any]) -> int:
    return int(terms["hours_per_day"]) * int(terms["days_per_week"])
