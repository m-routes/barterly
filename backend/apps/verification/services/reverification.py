"""Re-verification: changing a verified detail sends its case back to review.

Wired to profile saves in apps.verification.signals, so the profile API, the Django
admin and scripts all trigger it. The badge is revoked until a reviewer approves again.
"""

from django.db import transaction

from apps.verification.constants import CHECKS, CaseStatus
from apps.verification.models import VerificationCase
from apps.verification.services.cases import transition

LABELS = {
    "address": "property address",
    "business_name": "business name",
    "gstin": "GSTIN",
    "instagram_handle": "Instagram handle",
}


def watched_fields(role: str) -> set[str]:
    return {f for rule in CHECKS.get(role, {}).values() for f in rule.watched_fields}


def on_profile_changed(profile, changed: set[str], *, actor=None) -> list[VerificationCase]:
    """Reopen approved cases whose verified fields changed. Returns the cases moved."""
    user = profile.user
    moved = []
    with transaction.atomic():
        for check_type, rule in CHECKS.get(user.role, {}).items():
            fields = changed & set(rule.watched_fields)
            if not fields:
                continue
            case = (
                VerificationCase.objects.select_for_update()
                .select_related("user")
                .filter(user=user, check_type=check_type)
                .first()
            )
            if case is None:
                continue
            _refresh_subject(case, profile, fields)
            if case.status == CaseStatus.APPROVED:
                names = ", ".join(LABELS.get(f, f) for f in sorted(fields))
                transition(
                    case,
                    CaseStatus.IN_REVIEW,
                    actor=actor,
                    reason=f"Your {names} changed, so we're checking it again.",
                )
                moved.append(case)
            elif case.status in (CaseStatus.SUBMITTED, CaseStatus.IN_REVIEW):
                case.save(update_fields=["details", "subject_id", "updated_at"])
    return moved


def _refresh_subject(case: VerificationCase, profile, fields: set[str]) -> None:
    """Show the reviewer the new values (the details keep the same keys as at submission)."""
    details = dict(case.details)
    for name in fields:
        if name == "instagram_handle":
            details["handle"] = profile.instagram_handle
            case.subject_id = f"instagram:{profile.instagram_handle.lower()}"
        elif name == "gstin":
            details["gstin_last_four"] = (profile.gstin or "")[-4:]
        else:
            details[name] = getattr(profile, name)
    case.details = details
