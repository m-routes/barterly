"""Can this talent apply to this gig? Every failed check becomes a reason in a list, so
the app can show them all at once instead of one per attempt."""

from dataclasses import dataclass
from datetime import date, timedelta

from apps.accounts.models import Role
from apps.applications.constants import ACTIVE
from apps.applications.models import Application
from apps.gigs.constants import MIN_AGE_YEARS, GigStatus, RequiredVerification
from apps.profiles.models import age_on
from apps.verification.constants import BadgeKind
from apps.verification.services.cases import active_badge_kinds

MAX_ANSWER_LENGTH = 1000


@dataclass(frozen=True)
class Reason:
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


def gig_end(gig) -> date | None:
    if gig.end_date:
        return gig.end_date
    if gig.start_date and gig.duration_days:
        return gig.start_date + timedelta(days=gig.duration_days)
    return None


def blocking_reasons(
    talent,
    gig,
    profile,
    *,
    proposed_start: date,
    proposed_end: date,
    answers: list[str],
    today: date,
) -> list[Reason]:
    reasons: list[Reason] = []

    def block(code: str, message: str) -> None:
        reasons.append(Reason(code, message))

    if talent.role != Role.TALENT:
        block("not_talent", "Only talent accounts can apply to gigs.")
    if gig.vendor_id == talent.pk:
        block("own_gig", "You can't apply to your own gig.")
    if gig.status != GigStatus.LIVE or (gig.apply_by and gig.apply_by < today):
        block("gig_not_open", "This gig isn't taking applications.")

    if profile is None or profile.is_deleted:
        block("profile_incomplete", "Set up your talent profile first.")
    elif missing := profile.missing_fields():
        block("profile_incomplete", f"Finish your profile: {', '.join(missing)}.")

    badges = active_badge_kinds(talent)
    needed = gig.required_verification
    if needed == RequiredVerification.ID_VERIFIED and BadgeKind.ID_VERIFIED not in badges:
        block("verification_required", "This gig needs a verified ID.")
    if needed == RequiredVerification.TRUSTED_MEMBER and BadgeKind.TRUSTED_MEMBER not in badges:
        block("verification_required", "This gig is for trusted members only.")

    if Application.objects.filter(gig=gig, talent=talent, status__in=ACTIVE).exists():
        block("already_applied", "You already have an active application for this gig.")

    if profile is not None:
        if gig.languages and not set(gig.languages) & set(profile.languages or []):
            block("language_mismatch", f"This gig needs one of: {', '.join(gig.languages)}.")
        if gig.min_followers and (profile.instagram_followers or 0) < gig.min_followers:
            block(
                "not_enough_followers",
                f"This gig needs at least {gig.min_followers:,} followers.",
            )
        start = gig.start_date or proposed_start
        if profile.date_of_birth and age_on(profile.date_of_birth, start) < MIN_AGE_YEARS:
            block("under_age", f"You must be at least {MIN_AGE_YEARS} when the gig starts.")

    reasons += _date_reasons(gig, proposed_start, proposed_end, today)

    questions = gig.screening_questions or []
    if len(answers) != len(questions) or any(not a.strip() for a in answers):
        block("answers_missing", f"Answer all {len(questions)} screening questions.")
    elif any(len(a) > MAX_ANSWER_LENGTH for a in answers):
        block("answer_too_long", f"Keep each answer under {MAX_ANSWER_LENGTH} characters.")
    return reasons


def _date_reasons(gig, start: date, end: date, today: date) -> list[Reason]:
    if end <= start:
        return [Reason("dates_invalid", "Your end date must be after your start date.")]
    reasons = []
    if start < today:
        reasons.append(Reason("dates_invalid", "Your start date has passed."))
    last_day = gig_end(gig)
    if (gig.start_date and start < gig.start_date) or (last_day and end > last_day):
        window = f"{gig.start_date:%d %b %Y}" + (f" to {last_day:%d %b %Y}" if last_day else "")
        reasons.append(Reason("dates_outside_gig", f"Pick dates within the gig: {window}."))
    if gig.min_stay_days and (end - start).days < gig.min_stay_days:
        reasons.append(
            Reason("stay_too_short", f"This gig needs a stay of at least {gig.min_stay_days} days.")
        )
    return reasons
