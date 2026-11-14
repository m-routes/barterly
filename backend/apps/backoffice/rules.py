"""The gig rules, laid out for a reviewer: each rule, the gig's value, and whether it
holds. Breaks come from apps.gigs.rules.check_complete, the same check that runs when
a gig goes live, so the page and the approve button never disagree."""

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.gigs.constants import (
    DELIVERABLE_MODELS,
    MAX_DAYS_PER_WEEK,
    MAX_HOURS_PER_DAY,
    MIN_AGE_YEARS,
    STIPEND_MODELS,
    CompensationModel,
)
from apps.gigs.rules import check_complete, gig_length_days
from apps.verification.constants import BadgeKind, CaseStatus

EMPTY = "\u2013"  # en dash for "not set"


@dataclass
class RuleRow:
    rule: str
    value: str
    fields: tuple[str, ...] = ()
    applies: bool = True
    problems: list[str] = field(default_factory=list)

    @property
    def broken(self) -> bool:
        return bool(self.problems)


@dataclass
class RuleReport:
    rows: list[RuleRow]
    other_problems: list[str]
    warnings: list[str]

    @property
    def breaks(self) -> int:
        return sum(r.broken for r in self.rows) + len(self.other_problems)


def _shown(value) -> str:
    return EMPTY if value in (None, "", []) else str(value)


def gig_rules(gig, today=None) -> RuleReport:
    today = today or timezone.localdate()
    try:
        check_complete(gig, today)
        errors: dict[str, list[str]] = {}
    except ValidationError as exc:
        errors = exc.message_dict

    model = gig.compensation_model
    length = gig_length_days(gig)
    rows = [
        RuleRow(
            f"At most {MAX_HOURS_PER_DAY} hours a day",
            _shown(gig.hours_per_day),
            ("hours_per_day",),
        ),
        RuleRow(
            f"At least one day off (at most {MAX_DAYS_PER_WEEK} days a week)",
            _shown(gig.days_per_week),
            ("days_per_week",),
        ),
        RuleRow(f"Talent are {MIN_AGE_YEARS} or older", f"{MIN_AGE_YEARS}+ (fixed)"),
        RuleRow(
            "Starts in the future, after applications close",
            f"start {_shown(gig.start_date)}, apply by {_shown(gig.apply_by)}",
            ("start_date", "apply_by"),
        ),
        RuleRow(
            "Has an end date or a length",
            f"{length} days" if length else EMPTY,
            ("end_date", "duration_days", "min_stay_days"),
        ),
        RuleRow(
            "Says where talent stay and what they eat",
            f"{gig.get_stay_type_display() or EMPTY}, {gig.get_meals_display() or EMPTY}",
            ("stay_type", "meals"),
        ),
        RuleRow(
            "Stipend above zero, with a period",
            f"₹{gig.stipend_amount} {gig.get_stipend_period_display()}"
            if gig.stipend_amount
            else EMPTY,
            ("stipend_amount", "stipend_period"),
            applies=model in STIPEND_MODELS,
        ),
        RuleRow(
            "Lists what the talent will create",
            f"{len(gig.deliverables or [])} deliverable(s)",
            ("deliverables",),
            applies=model in DELIVERABLE_MODELS,
        ),
        RuleRow(
            "Title, description and screening questions are filled in properly",
            f"{len(gig.screening_questions or [])} question(s)",
            ("title", "description", "screening_questions", "languages"),
        ),
    ]
    covered: set[str] = set()
    for row in rows:
        for name in row.fields:
            covered.add(name)
            if row.applies:
                row.problems += errors.get(name, [])
    other = [
        f"{name}: {message}"
        for name, messages in errors.items()
        if name not in covered
        for message in messages
    ]
    return RuleReport(
        rows=[r for r in rows if r.applies], other_problems=other, warnings=_warnings(gig)
    )


def _warnings(gig) -> list[str]:
    """Not rule breaks, but worth a look before approving."""
    notes = []
    if gig.property.verification_status != CaseStatus.APPROVED:
        notes.append(
            f"The property isn't verified ({gig.property.get_verification_status_display()})."
        )
    if not gig.vendor.badges.filter(kind=BadgeKind.ID_VERIFIED, revoked_at__isnull=True).exists():
        notes.append("The host hasn't verified their ID.")
    if (
        gig.compensation_model == CompensationModel.VOLUNTEER
        and gig.hours_per_day
        and gig.days_per_week
        and gig.hours_per_day * gig.days_per_week > 30
    ):
        notes.append(
            f"{gig.hours_per_day * gig.days_per_week} hours a week is a lot for a stay-only gig."
        )
    return notes
