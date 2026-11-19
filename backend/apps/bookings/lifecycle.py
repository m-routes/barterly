"""THE transition table for an engagement, from application to booking.

An application moves applied → shortlisted → interview → offered. When an offer is
accepted (offered → confirmed: the talent accepts the host's offer, or the host accepts
the talent's counter; see apps.offers) a Booking is created awaiting signatures. It is
confirmed, and takes one of the gig's slots, only when both sides have signed the
agreement (apps.bookings.confirmation). The booking then carries on: confirmed →
checked_in → delivering → completed → reviewed, with cancelled, no_show, disputed and
refunded along the way.

Every allowed move is one row of TRANSITIONS: who may make it and the guard that must
pass. Nothing else in the code decides whether a status change is allowed; the
services call check() and the API and admin go through the services.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from django.db import models
from django.utils import timezone

from apps.applications.constants import ACTIVE, ApplicationStatus

OFFER_TTL = timedelta(hours=48)
STALE_INTERVIEW_AFTER = timedelta(days=7)
DISPUTE_WINDOW = timedelta(days=14)
CHECK_IN_EARLY = timedelta(days=1)


class BookingStatus(models.TextChoices):
    SIGNING = "signing", "Awaiting signatures"
    CONFIRMED = "confirmed", "Confirmed"
    CHECKED_IN = "checked_in", "Checked in"
    DELIVERING = "delivering", "Delivering"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "No-show"
    DISPUTED = "disputed", "Disputed"
    REFUNDED = "refunded", "Refunded"
    REVIEWED = "reviewed", "Reviewed"


class Actor(models.TextChoices):
    TALENT = "talent", "The talent"
    VENDOR = "vendor", "The gig's vendor"
    SYSTEM = "system", "A scheduled job or another service"
    ADMIN = "admin", "Barterly admin"


A, B = ApplicationStatus, BookingStatus
T, V, SYS, ADM = Actor.TALENT, Actor.VENDOR, Actor.SYSTEM, Actor.ADMIN

# Bookings in these states hold one of the gig's slots.
HOLDS_SLOT = frozenset(
    {B.CONFIRMED, B.CHECKED_IN, B.DELIVERING, B.COMPLETED, B.DISPUTED, B.REVIEWED}
)
# Bookings in these states keep the talent's dates: no second booking may overlap them.
HOLDS_DATES = HOLDS_SLOT | {B.SIGNING}
# Cancelling a booking in these states is "before check-in" (apps.bookings.cancellation).
BEFORE_CHECK_IN = frozenset({B.SIGNING, B.CONFIRMED})


class GuardFailed(Exception):
    """The move exists and the actor may make it, but not right now (the message says why)."""


@dataclass(frozen=True)
class Context:
    """What a guard can look at: the application or booking, and the moment."""

    subject: Any  # Application, or Booking
    actor: str
    reason: str = ""
    now: datetime = field(default_factory=timezone.now)

    @property
    def today(self) -> date:
        return timezone.localdate(self.now)


Guard = Callable[[Context], str | None]  # None: allowed. A string: why not.


@dataclass(frozen=True)
class Rule:
    actors: frozenset[str]
    guard: Guard | None = None
    needs_reason: bool = False
    note: str = ""


# ---------- Guards ----------


def _gig_running(ctx: Context) -> str | None:
    from apps.gigs.constants import GigStatus

    gig = ctx.subject.gig
    if gig.status not in (GigStatus.LIVE, GigStatus.PAUSED, GigStatus.FILLED):
        return f"The gig is {gig.get_status_display().lower()}."
    return None


def _open_slot(ctx: Context) -> str | None:
    """Callers hold the gig row lock (SELECT ... FOR UPDATE) while this counts."""
    from apps.bookings.models import Booking

    gig = ctx.subject.gig
    taken = Booking.objects.filter(gig=gig, status__in=HOLDS_SLOT).count()
    if taken >= gig.slots:
        return f"Every slot on this gig is taken ({taken} of {gig.slots})."
    return None


def _can_offer(ctx: Context) -> str | None:
    return _gig_running(ctx) or _open_slot(ctx)


def _can_accept(ctx: Context) -> str | None:
    """The booking's dates are the accepted offer's: bookings.services.confirm() puts them
    on the application as `booking_dates` before the move."""
    from apps.bookings.models import Booking

    application = ctx.subject
    if application.offer_expires_at and application.offer_expires_at <= ctx.now:
        return "This offer has expired."
    if problem := _open_slot(ctx):
        return problem
    start, end = getattr(
        application, "booking_dates", (application.proposed_start, application.proposed_end)
    )
    overlapping = Booking.objects.filter(
        talent_id=application.talent_id,
        status__in=HOLDS_DATES,
        start_date__lt=end,
        end_date__gt=start,
    )
    if overlapping.exists():
        return "You already have a booking for some of these dates."
    return None


def _offer_lapsed(ctx: Context) -> str | None:
    """The offer ran out of time, or every slot is taken (apps.bookings.confirmation
    expires the other offers when the gig fills, if settings say so)."""
    expires = ctx.subject.offer_expires_at
    if expires is not None and expires <= ctx.now:
        return None
    if _open_slot(ctx) is not None:
        return None
    return "The offer hasn't expired yet."


def _agreement_in_force(ctx: Context) -> str | None:
    from apps.agreements.models import Agreement

    if not Agreement.objects.filter(
        booking_id=ctx.subject.pk, current_version__isnull=False
    ).exists():
        return "Both of you need to sign the agreement before check-in."
    return None


def _signed_with_open_slot(ctx: Context) -> str | None:
    """Both signatures are in (apps.bookings.confirmation calls this inside signing)."""
    return _agreement_in_force(ctx) or _open_slot(ctx)


def _can_check_in(ctx: Context) -> str | None:
    return _check_in_window(ctx) or _agreement_in_force(ctx) or _stipend_funded(ctx)


def _stipend_funded(ctx: Context) -> str | None:
    """Paid and hybrid stays: the host's stipend must be held in escrow first."""
    from apps.money.escrow import require_funded

    return require_funded(ctx.subject)


def _check_in_window(ctx: Context) -> str | None:
    booking = ctx.subject
    if ctx.today < booking.start_date - CHECK_IN_EARLY:
        return f"Check-in opens the day before the stay starts ({booking.start_date:%d %b})."
    if ctx.today > booking.end_date:
        return "The stay has already ended."
    return None


def _stay_started(ctx: Context) -> str | None:
    if ctx.today < ctx.subject.start_date:
        return "The stay hasn't started yet."
    return None


def _within_dispute_window(ctx: Context) -> str | None:
    since = ctx.subject.status_changed_at
    if since and ctx.now - since > DISPUTE_WINDOW:
        return f"Disputes must be raised within {DISPUTE_WINDOW.days} days."
    return None


def _money_involved(ctx: Context) -> str | None:
    from apps.gigs.constants import STIPEND_MODELS

    if ctx.subject.gig.compensation_model not in STIPEND_MODELS:
        return "Only paid and hybrid gigs have money to refund."
    return None


# ---------- The table ----------

_ACTIVE_BEFORE_OFFER = (A.APPLIED, A.SHORTLISTED, A.INTERVIEW)

TRANSITIONS: dict[tuple[str, str], Rule] = {
    # Application: the vendor moves it along.
    (A.APPLIED, A.SHORTLISTED): Rule(frozenset({V}), _gig_running),
    (A.APPLIED, A.INTERVIEW): Rule(frozenset({V}), _gig_running),
    (A.SHORTLISTED, A.INTERVIEW): Rule(frozenset({V}), _gig_running),
    **{
        (s, A.OFFERED): Rule(frozenset({V}), _can_offer, note="Expires 48 hours after it is made.")
        for s in _ACTIVE_BEFORE_OFFER
    },
    # A place opened up: the system offers it to the next shortlisted applicant on the
    # terms the host agreed before (apps.bookings.cancellation.offer_place).
    (A.SHORTLISTED, A.OFFERED): Rule(
        frozenset({V, SYS}), _can_offer, note="Also sent automatically when a place opens."
    ),
    **{(s, A.REJECTED): Rule(frozenset({V})) for s in ACTIVE},
    # Auto-reject rules: the system turns down a new application that misses them.
    (A.APPLIED, A.REJECTED): Rule(frozenset({V, SYS})),
    # The talent: withdraw any time until accepting; answer an offer.
    **{(s, A.WITHDRAWN): Rule(frozenset({T})) for s in ACTIVE},
    (A.OFFERED, A.DECLINED): Rule(frozenset({T})),
    (A.OFFERED, A.CONFIRMED): Rule(
        frozenset({T, V}),
        _can_accept,
        note="Creates the booking. The host confirms only by accepting the talent's counter.",
    ),
    # The system: an unanswered offer lapses; a closed or filled gig ends the rest.
    (A.OFFERED, A.EXPIRED): Rule(frozenset({SYS}), _offer_lapsed),
    **{(s, A.EXPIRED): Rule(frozenset({SYS})) for s in _ACTIVE_BEFORE_OFFER},
    # Booking. Confirmed when both have signed; either side may call it off before then.
    (B.SIGNING, B.CONFIRMED): Rule(
        frozenset({SYS}), _signed_with_open_slot, note="When both sides have signed."
    ),
    (B.SIGNING, B.CANCELLED): Rule(frozenset({T, V, SYS, ADM}), needs_reason=True),
    (B.CONFIRMED, B.CHECKED_IN): Rule(
        frozenset({V}),
        _can_check_in,
        note="Needs the agreement signed by both; paid and hybrid gigs, the stipend funded.",
    ),
    (B.CONFIRMED, B.CANCELLED): Rule(frozenset({T, V, ADM}), needs_reason=True),
    (B.CONFIRMED, B.NO_SHOW): Rule(frozenset({V}), _stay_started, needs_reason=True),
    (B.CHECKED_IN, B.DELIVERING): Rule(frozenset({T, V})),
    (B.CHECKED_IN, B.CANCELLED): Rule(frozenset({ADM}), needs_reason=True),
    (B.DELIVERING, B.COMPLETED): Rule(frozenset({V, SYS}), _stay_started),
    (B.DELIVERING, B.DISPUTED): Rule(frozenset({T, V}), needs_reason=True),
    (B.COMPLETED, B.DISPUTED): Rule(frozenset({T, V}), _within_dispute_window, needs_reason=True),
    (B.COMPLETED, B.REVIEWED): Rule(frozenset({T, V})),
    (B.NO_SHOW, B.DISPUTED): Rule(frozenset({T}), _within_dispute_window, needs_reason=True),
    (B.DISPUTED, B.COMPLETED): Rule(frozenset({ADM}), needs_reason=True),
    (B.DISPUTED, B.CANCELLED): Rule(frozenset({ADM}), needs_reason=True),
    (B.DISPUTED, B.REFUNDED): Rule(frozenset({ADM}), _money_involved, needs_reason=True),
    (B.CANCELLED, B.REFUNDED): Rule(frozenset({ADM, SYS}), _money_involved, needs_reason=True),
}


class InvalidTransition(Exception):
    """The move doesn't exist, or this actor may not make it."""


def check(frm: str, to: str, ctx: Context) -> Rule:
    """Raise unless TRANSITIONS allows `ctx.actor` to move from `frm` to `to` now."""
    rule = TRANSITIONS.get((frm, to))
    if rule is None:
        raise InvalidTransition(f"Can't go from {frm} to {to}.")
    if ctx.actor not in rule.actors:
        raise InvalidTransition(f"Only the {' or '.join(sorted(rule.actors))} can do that.")
    if rule.needs_reason and not ctx.reason.strip():
        raise GuardFailed("Give a reason.")
    if rule.guard and (problem := rule.guard(ctx)):
        raise GuardFailed(problem)
    return rule


def moves_from(state: str, actor: str) -> list[str]:
    """States `actor` could move to from `state` (guards not checked)."""
    return sorted(
        to for (frm, to), rule in TRANSITIONS.items() if frm == state and actor in rule.actors
    )
