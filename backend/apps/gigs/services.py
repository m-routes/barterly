"""Creating, editing and moving gigs. Every status change writes an AuditLog row.

Rules are checked here (apps.gigs.rules), whatever the caller: API, admin or job.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.common.services.audit import log_action, snapshot
from apps.gigs.constants import (
    EDITABLE,
    MONEY_FIELDS,
    REVIEWED_FIELDS,
    TRANSITIONS,
    Actor,
    GigStatus,
)
from apps.gigs.models import Gig
from apps.gigs.plans import get_plan_policy
from apps.gigs.rules import check_complete, check_shape

STATUS_AUDIT_FIELDS = ["status", "status_reason"]
DATE_FIELDS = frozenset({"start_date", "end_date", "duration_days", "apply_by"})


class InvalidGigTransition(Exception):
    """That status change doesn't exist, or this actor may not make it."""


class GigLocked(Exception):
    """Filled, closed and archived gigs can't be edited."""


class PlanLimitReached(Exception):
    """The vendor's plan allows no more live gigs."""


def actor_for(user, gig: Gig) -> str | None:
    if user.pk == gig.vendor_id:
        return Actor.VENDOR
    if getattr(user, "is_admin_role", False):
        return Actor.ADMIN
    return None


def create_gig(vendor, data: dict, *, request=None) -> Gig:
    gig = Gig(vendor=vendor, **data)
    check_shape(gig)
    with transaction.atomic():
        gig.save()
        log_action(
            actor=vendor,
            action="gig.created",
            obj=gig,
            after=snapshot(gig, [*STATUS_AUDIT_FIELDS, *MONEY_FIELDS]),
            request=request,
        )
    return gig


def update_gig(gig_id, data: dict, *, user, request=None) -> Gig:
    """Apply an edit. Changing pay, hours or dates of a live or paused gig sends it back
    to review."""
    with transaction.atomic():
        gig = Gig.objects.select_for_update().select_related("property").get(pk=gig_id)
        if gig.status not in EDITABLE:
            raise GigLocked(f"A {gig.get_status_display().lower()} gig can't be edited.")
        before = {name: getattr(gig, name) for name in data}
        money_before = snapshot(gig, MONEY_FIELDS)
        for name, value in data.items():
            setattr(gig, name, value)
        changed = {name for name in data if getattr(gig, name) != before[name]}

        if gig.status == GigStatus.DRAFT:
            check_shape(gig)
        else:
            # Past draft the gig must stay complete. Dates already in the past are fine
            # unless this edit moved them.
            check_complete(gig, check_dates=bool(changed & DATE_FIELDS))
        gig.save()

        money_after = snapshot(gig, MONEY_FIELDS)
        if money_after != money_before:
            log_action(
                actor=user,
                action="gig.compensation_changed",
                obj=gig,
                before=money_before,
                after=money_after,
                request=request,
            )
        reviewed = sorted(changed & REVIEWED_FIELDS)
        if reviewed and gig.status in (GigStatus.LIVE, GigStatus.PAUSED):
            labels = ", ".join(name.replace("_", " ") for name in reviewed)
            _move(
                gig,
                GigStatus.IN_REVIEW,
                actor=Actor.SYSTEM,
                user=user,
                reason=f"Changed {labels}; Barterly reviews it again before it goes back live.",
                request=request,
            )
    return gig


def transition(gig_id, to: str, *, actor: str, user=None, reason: str = "", request=None) -> Gig:
    """Move a gig to `to` if TRANSITIONS lets this actor do it."""
    with transaction.atomic():
        gig = Gig.objects.select_for_update().select_related("property").get(pk=gig_id)
        return _move(gig, to, actor=actor, user=user, reason=reason, request=request)


def _move(gig: Gig, to: str, *, actor: str, user=None, reason: str = "", request=None) -> Gig:
    allowed = TRANSITIONS.get((gig.status, to))
    if allowed is None:
        raise InvalidGigTransition(f"A {gig.status} gig can't become {to}.")
    if actor not in allowed:
        raise InvalidGigTransition(
            f"Only {', '.join(sorted(allowed))} can make a {gig.status} gig {to}."
        )
    reason = reason.strip()
    sent_back = gig.status == GigStatus.IN_REVIEW and to == GigStatus.DRAFT
    if sent_back and actor == Actor.ADMIN and not reason:
        raise ValueError("Say what the vendor needs to change.")

    if to == GigStatus.IN_REVIEW and gig.status == GigStatus.DRAFT:
        check_complete(gig)
    if to == GigStatus.LIVE and gig.status in (GigStatus.IN_REVIEW, GigStatus.PAUSED):
        check_complete(gig, check_dates=gig.status == GigStatus.IN_REVIEW)
        if gig.apply_by and gig.apply_by < timezone.localdate():
            raise ValidationError({"apply_by": ["Applications have closed; edit the dates first."]})
        _check_plan(gig)

    before = snapshot(gig, STATUS_AUDIT_FIELDS)
    now = timezone.now()
    gig.status = to
    gig.status_reason = reason
    if to == GigStatus.IN_REVIEW:
        gig.submitted_at = now
    elif to == GigStatus.LIVE and gig.published_at is None:
        gig.published_at = now
    elif to == GigStatus.CLOSED:
        gig.closed_at = now
    gig.save()
    log_action(
        actor=user,
        action=f"gig.{to}",
        obj=gig,
        before=before,
        after={**snapshot(gig, STATUS_AUDIT_FIELDS), "by": actor},
        request=request,
    )
    return gig


def _check_plan(gig: Gig) -> None:
    plan = get_plan_policy().plan_for(gig.vendor)
    if plan.max_live_gigs is None:
        return
    live = Gig.objects.filter(vendor_id=gig.vendor_id, status=GigStatus.LIVE).exclude(pk=gig.pk)
    if live.count() >= plan.max_live_gigs:
        raise PlanLimitReached(
            f"Your {plan.name} plan allows {plan.max_live_gigs} live gigs. "
            "Pause or close one first."
        )


def close_expired_gigs(today=None) -> int:
    """Scheduled job: close live and paused gigs whose apply-by date has passed."""
    today = today or timezone.localdate()
    due = Gig.objects.filter(
        status__in=[GigStatus.LIVE, GigStatus.PAUSED], apply_by__lt=today
    ).values_list("pk", flat=True)
    closed = 0
    for gig_id in due:
        with transaction.atomic():
            gig = (
                Gig.objects.select_for_update()
                .filter(
                    pk=gig_id, status__in=[GigStatus.LIVE, GigStatus.PAUSED], apply_by__lt=today
                )
                .first()
            )
            if gig is None:
                continue
            _move(gig, GigStatus.CLOSED, actor=Actor.SYSTEM, reason="Applications closed.")
            closed += 1
    return closed


def on_confirmed_bookings_changed(gig_id, confirmed: int) -> Gig:
    """Hook for bookings (Phase 3): fill a gig when confirmed bookings reach its slots,
    and reopen it if one is cancelled before applications close."""
    with transaction.atomic():
        gig = Gig.objects.select_for_update().get(pk=gig_id)
        if gig.status == GigStatus.LIVE and confirmed >= gig.slots:
            return _move(gig, GigStatus.FILLED, actor=Actor.SYSTEM, reason="Every slot is booked.")
        still_open = gig.apply_by is None or gig.apply_by >= timezone.localdate()
        if gig.status == GigStatus.FILLED and confirmed < gig.slots and still_open:
            return _move(gig, GigStatus.LIVE, actor=Actor.SYSTEM, reason="A slot opened up.")
        return gig
