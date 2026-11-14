"""Case lifecycle and badges. Every status change and badge change is audit-logged.

Callers hold the case row lock (`locked_case`) inside a transaction, so two reviewers
or a reviewer and a webhook can't both move the same case.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.common.services.audit import log_action, snapshot
from apps.properties.models import Property
from apps.verification.constants import (
    DECIDABLE,
    TRANSITIONS,
    TRUSTED_MEMBER_REQUIRES,
    BadgeKind,
    CaseStatus,
    CheckType,
    rule_for,
)
from apps.verification.models import Badge, VerificationCase

CASE_AUDIT_FIELDS = ["status", "reason", "reviewer", "expires_at"]


class CheckNotAvailable(Exception):
    """This check doesn't apply to the user's role."""


class InvalidTransition(Exception):
    """The case can't move to that status from where it is now."""


class Decision:
    START_REVIEW = "start_review"
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    REVOKE = "revoke"
    CHOICES = (START_REVIEW, APPROVE, REJECT, REQUEST_CHANGES, REVOKE)
    NEEDS_REASON = frozenset({REJECT, REQUEST_CHANGES, REVOKE})


def locked_case(user, check_type: str, *, prop=None) -> VerificationCase:
    """The user's case for this check (per property for the property check), created on
    first use and locked. Needs a transaction."""
    rule = rule_for(user.role, check_type)
    if rule is None:
        raise CheckNotAvailable(f"{check_type} isn't a check for {user.role or 'this account'}.")
    if (check_type == CheckType.PROPERTY) != (prop is not None):
        raise ValueError("The property check, and only it, is per property.")
    case, _ = VerificationCase.objects.get_or_create(
        user=user,
        check_type=check_type,
        property=prop,
        defaults={"subject_type": rule.subject, "subject_id": str(prop.pk) if prop else ""},
    )
    return VerificationCase.objects.select_for_update().get(pk=case.pk)


def transition(case: VerificationCase, new_status: str, *, actor, reason: str = "", request=None):
    """Move a locked case to new_status, keeping badges in step."""
    old_status = case.status
    if new_status not in TRANSITIONS[old_status]:
        raise InvalidTransition(f"A {old_status} case can't become {new_status}.")
    before = snapshot(case, CASE_AUDIT_FIELDS)
    now = timezone.now()
    rule = rule_for(case.user.role, case.check_type)
    reviewer = actor if getattr(actor, "is_admin_role", False) else None

    case.status = new_status
    case.reason = reason
    if new_status == CaseStatus.SUBMITTED:
        case.submitted_at = now
        case.reviewer = None
    elif new_status == CaseStatus.APPROVED:
        case.reviewer = reviewer
        case.reviewed_at = case.approved_at = now
        case.expires_at = now + timedelta(days=rule.valid_days) if rule else None
    elif new_status in (CaseStatus.REJECTED, CaseStatus.CHANGES_REQUESTED):
        case.reviewer = reviewer
        case.reviewed_at = now
        case.expires_at = None
    elif new_status == CaseStatus.IN_REVIEW and reviewer is not None:
        case.reviewer = reviewer
    case.save()
    if case.property_id:
        Property.all_objects.filter(pk=case.property_id).update(verification_status=new_status)

    log_action(
        actor=actor,
        action=f"verification.case.{new_status}",
        obj=case,
        before=before,
        after=snapshot(case, CASE_AUDIT_FIELDS),
        request=request,
    )

    leaving_approved = old_status == CaseStatus.APPROVED and new_status != CaseStatus.APPROVED
    if rule is not None and leaving_approved and not _badge_still_earned(case, rule.badge):
        revoke_badge(
            case.user,
            rule.badge,
            actor=actor,
            reason=reason or f"Case {new_status}.",
            request=request,
        )
    if rule is not None and new_status == CaseStatus.APPROVED:
        grant_badge(
            case.user,
            rule.badge,
            case=case,
            actor=actor,
            reason=reason or f"{case.get_check_type_display()} approved.",
            request=request,
        )
    return case


def _badge_still_earned(case: VerificationCase, badge: str) -> bool:
    """Another approved case of the user's earns the same badge (e.g. a second property)."""
    others = VerificationCase.objects.filter(user=case.user, status=CaseStatus.APPROVED).exclude(
        pk=case.pk
    )
    return any(
        (rule := rule_for(case.user.role, check)) is not None and rule.badge == badge
        for check in others.values_list("check_type", flat=True)
    )


def withdraw_property(prop, *, actor, request=None) -> None:
    """The property was removed: its verification no longer stands."""
    case = (
        VerificationCase.objects.select_for_update()
        .select_related("user")
        .filter(property=prop)
        .first()
    )
    if case is None:
        return
    reason = "The property was removed."
    if case.status == CaseStatus.APPROVED:
        transition(case, CaseStatus.EXPIRED, actor=actor, reason=reason, request=request)
    elif case.status in DECIDABLE:
        transition(case, CaseStatus.REJECTED, actor=actor, reason=reason, request=request)


def grant_badge(user, kind: str, *, case=None, actor=None, reason: str, request=None) -> Badge:
    """Grant a badge (no-op if already active), then recheck trusted member."""
    badge = Badge.objects.filter(user=user, kind=kind, revoked_at__isnull=True).first()
    if badge is None:
        badge = Badge.objects.create(
            user=user,
            kind=kind,
            case=case,
            granted_at=timezone.now(),
            granted_by=actor if getattr(actor, "is_authenticated", False) else None,
            grant_reason=reason[:300],
        )
        log_action(
            actor=actor,
            action="verification.badge.granted",
            obj=badge,
            after={"user": str(user.pk), "kind": kind, "reason": reason[:300]},
            request=request,
        )
    if kind != BadgeKind.TRUSTED_MEMBER:
        sync_trusted_member(user, actor=actor, request=request)
    return badge


def revoke_badge(user, kind: str, *, actor=None, reason: str, request=None) -> Badge | None:
    """Revoke the active badge of this kind (no-op if none), then recheck trusted member."""
    badge = (
        Badge.objects.select_for_update()
        .filter(user=user, kind=kind, revoked_at__isnull=True)
        .first()
    )
    if badge is not None:
        badge.revoked_at = timezone.now()
        badge.revoked_by = actor if getattr(actor, "is_authenticated", False) else None
        badge.revoke_reason = reason[:300] or "Revoked."
        badge.save(update_fields=["revoked_at", "revoked_by", "revoke_reason", "updated_at"])
        log_action(
            actor=actor,
            action="verification.badge.revoked",
            obj=badge,
            before={"active": True},
            after={"active": False, "reason": badge.revoke_reason},
            request=request,
        )
    if kind != BadgeKind.TRUSTED_MEMBER:
        sync_trusted_member(user, actor=actor, request=request)
    return badge


def active_badge_kinds(user) -> set[str]:
    return set(
        Badge.objects.filter(user=user, revoked_at__isnull=True).values_list("kind", flat=True)
    )


def sync_trusted_member(user, *, actor=None, request=None) -> None:
    """Trusted member is held exactly while every required badge for the role is."""
    required = TRUSTED_MEMBER_REQUIRES.get(user.role)
    if not required:
        return
    kinds = active_badge_kinds(user)
    has_all = required <= kinds
    if has_all and BadgeKind.TRUSTED_MEMBER not in kinds:
        grant_badge(
            user,
            BadgeKind.TRUSTED_MEMBER,
            actor=actor,
            reason="Every required check is approved.",
            request=request,
        )
    elif not has_all and BadgeKind.TRUSTED_MEMBER in kinds:
        missing = ", ".join(sorted(required - kinds))
        revoke_badge(
            user,
            BadgeKind.TRUSTED_MEMBER,
            actor=actor,
            reason=f"No longer holds: {missing}.",
            request=request,
        )


def decide(case_id, decision: str, *, reviewer, reason: str = "", request=None) -> VerificationCase:
    """A trust reviewer's decision on a case."""
    if decision in Decision.NEEDS_REASON and not reason.strip():
        raise ValueError("Give a reason the user can act on.")
    with transaction.atomic():
        case = VerificationCase.objects.select_for_update().select_related("user").get(pk=case_id)
        if decision == Decision.REVOKE:
            if case.status != CaseStatus.APPROVED:
                raise InvalidTransition("Only an approved case can be revoked.")
            return transition(
                case, CaseStatus.REJECTED, actor=reviewer, reason=reason, request=request
            )
        if case.status not in DECIDABLE:
            raise InvalidTransition(f"A {case.status} case isn't waiting for a decision.")
        target = {
            Decision.START_REVIEW: CaseStatus.IN_REVIEW,
            Decision.APPROVE: CaseStatus.APPROVED,
            Decision.REJECT: CaseStatus.REJECTED,
            Decision.REQUEST_CHANGES: CaseStatus.CHANGES_REQUESTED,
        }[decision]
        return transition(case, target, actor=reviewer, reason=reason.strip(), request=request)


def expire_due_cases(now=None) -> int:
    """Expire approved cases past their expiry date. Returns how many."""
    now = now or timezone.now()
    count = 0
    due = VerificationCase.objects.filter(status=CaseStatus.APPROVED, expires_at__lte=now)
    for case_id in due.values_list("pk", flat=True):
        with transaction.atomic():
            case = (
                VerificationCase.objects.select_for_update()
                .select_related("user")
                .filter(pk=case_id, status=CaseStatus.APPROVED, expires_at__lte=now)
                .first()
            )
            if case is None:
                continue
            transition(
                case,
                CaseStatus.EXPIRED,
                actor=None,
                reason="Verification expired. Please verify again.",
            )
            count += 1
    return count
