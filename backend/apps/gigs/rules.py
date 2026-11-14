"""Gig business rules, enforced by the service layer (not only by forms).

check_shape() holds for every save, drafts included: the parts that are filled in must
make sense. check_complete() also holds before a gig can be reviewed or go live, and
after every edit of a gig past draft.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.gigs.constants import (
    DELIVERABLE_MODELS,
    MAX_DAYS_PER_WEEK,
    MAX_DELIVERABLES,
    MAX_HOURS_PER_DAY,
    MAX_SCREENING_QUESTIONS,
    STIPEND_MODELS,
    CompensationModel,
    DeliverableType,
    StayType,
)
from apps.profiles.constants import LANGUAGES

MAX_GIG_DAYS = 365


class Errors:
    def __init__(self) -> None:
        self.errors: dict[str, list[str]] = {}

    def add(self, field: str, message: str) -> None:
        self.errors.setdefault(field, []).append(message)

    def raise_if_any(self) -> None:
        if self.errors:
            raise ValidationError(self.errors)


def check_shape(gig) -> None:
    """Rules for the fields that are set. Drafts may leave fields empty."""
    errors = Errors()
    if gig.slots is not None and gig.slots < 1:
        errors.add("slots", "At least 1 slot.")
    if gig.hours_per_day is not None and not 1 <= gig.hours_per_day <= MAX_HOURS_PER_DAY:
        errors.add("hours_per_day", f"At most {MAX_HOURS_PER_DAY} hours a day.")
    if gig.days_per_week is not None and not 1 <= gig.days_per_week <= MAX_DAYS_PER_WEEK:
        errors.add("days_per_week", "Give at least one day off a week (at most 6 working days).")
    if gig.stipend_amount is not None:
        if gig.compensation_model not in STIPEND_MODELS:
            errors.add("stipend_amount", "Only hybrid and paid gigs have a stipend.")
        elif gig.stipend_amount <= Decimal(0):
            errors.add("stipend_amount", "The stipend must be more than zero.")
    if gig.deliverables:
        if gig.compensation_model not in DELIVERABLE_MODELS:
            errors.add("deliverables", "Only barter and hybrid gigs ask for deliverables.")
        _check_deliverables(gig.deliverables, errors)
    _check_list_of_codes(gig.languages, LANGUAGES, "languages", errors)
    _check_questions(gig.screening_questions, errors)
    if gig.end_date and gig.duration_days:
        errors.add("end_date", "Give an end date or a duration, not both.")
    if gig.start_date and gig.end_date and gig.end_date <= gig.start_date:
        errors.add("end_date", "The end date must be after the start date.")
    if gig.duration_days is not None and not 1 <= gig.duration_days <= MAX_GIG_DAYS:
        errors.add("duration_days", f"Between 1 and {MAX_GIG_DAYS} days.")
    if gig.apply_by and gig.start_date and gig.apply_by > gig.start_date:
        errors.add("apply_by", "Applications must close on or before the start date.")
    length = gig_length_days(gig)
    if gig.min_stay_days is not None and length is not None and gig.min_stay_days > length:
        errors.add("min_stay_days", "The minimum stay can't be longer than the gig.")
    if gig.property_id and (gig.property.vendor_id != gig.vendor_id or gig.property.is_deleted):
        errors.add("property", "Pick one of your own properties.")
    errors.raise_if_any()


def check_complete(gig, today: date | None = None, *, check_dates: bool = True) -> None:
    """Everything a gig needs before review and while it is live.

    check_dates=False skips "start in the future" and "apply-by not passed", for edits
    of a live gig that didn't touch its dates.
    """
    today = today or timezone.localdate()
    errors = Errors()
    try:
        check_shape(gig)
    except ValidationError as exc:  # report shape and completeness problems together
        for field, messages in exc.message_dict.items():
            for message in messages:
                errors.add(field, message)
    required = {
        "title": gig.title.strip(),
        "description": gig.description.strip(),
        "start_date": gig.start_date,
        "apply_by": gig.apply_by,
        "hours_per_day": gig.hours_per_day,
        "days_per_week": gig.days_per_week,
        "stay_type": gig.stay_type,
        "meals": gig.meals,
    }
    for field, value in required.items():
        if not value:
            errors.add(field, "Required before the gig can be reviewed.")
    if not (gig.end_date or gig.duration_days):
        errors.add("end_date", "Give an end date or a duration.")
    if check_dates and gig.start_date and gig.start_date <= today:
        errors.add("start_date", "The start date must be in the future.")
    if check_dates and gig.apply_by and gig.apply_by < today:
        errors.add("apply_by", "The apply-by date has passed.")

    model = gig.compensation_model
    if model == CompensationModel.VOLUNTEER:
        if gig.stay_type in ("", StayType.NONE):
            errors.add("stay_type", "Volunteer gigs must say where volunteers stay.")
        if not gig.meals:
            errors.add("meals", "Volunteer gigs must say which meals are included.")
    if model == CompensationModel.BARTER and not gig.deliverables:
        errors.add("deliverables", "Barter gigs need at least one deliverable.")
    if model in STIPEND_MODELS:
        if not gig.stipend_amount or gig.stipend_amount <= 0:
            errors.add("stipend_amount", "Hybrid and paid gigs need a stipend above zero.")
        if not gig.stipend_period:
            errors.add("stipend_period", "Say whether the stipend is per week, per month or total.")
    if model == CompensationModel.HYBRID and gig.stay_type in ("", StayType.NONE):
        errors.add("stay_type", "Hybrid gigs include a stay: say what kind.")
    errors.raise_if_any()


def gig_length_days(gig) -> int | None:
    if gig.duration_days:
        return gig.duration_days
    if gig.start_date and gig.end_date:
        return (gig.end_date - gig.start_date).days
    return None


def _check_deliverables(items, errors: Errors) -> None:
    if not isinstance(items, list) or len(items) > MAX_DELIVERABLES:
        errors.add("deliverables", f"Send a list of at most {MAX_DELIVERABLES} deliverables.")
        return
    for item in items:
        if (
            not isinstance(item, dict)
            or item.get("type") not in DeliverableType.values
            or not isinstance(item.get("quantity"), int)
            or not 1 <= item["quantity"] <= 50
            or len(str(item.get("notes", ""))) > 300
        ):
            errors.add(
                "deliverables",
                "Each deliverable needs a known type, a quantity from 1 to 50 and short notes.",
            )
            return


def _check_list_of_codes(items, allowed, field: str, errors: Errors) -> None:
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        errors.add(field, "Send a list of codes.")
    elif unknown := sorted(set(items) - set(allowed)):
        errors.add(field, f"Unknown: {', '.join(unknown)}.")


def _check_questions(items, errors: Errors) -> None:
    if (
        not isinstance(items, list)
        or len(items) > MAX_SCREENING_QUESTIONS
        or not all(isinstance(q, str) and 0 < len(q.strip()) <= 300 for q in items)
    ):
        errors.add(
            "screening_questions",
            f"At most {MAX_SCREENING_QUESTIONS} questions of up to 300 characters.",
        )
