"""The closed-beta limits, enforced while the `closed_beta` flag is on.

- Invite codes: signing up as a role in BETA_INVITE_ROLES needs a code (invites.py).
- Live gigs: a host can have at most BETA_MAX_LIVE_GIGS_PER_VENDOR live at once, even
  when their plan allows more (BetaPlanPolicy wraps the billing plan).
- Escrow: a booking's stipend can be at most BETA_MAX_STIPEND_RUPEES. Offers above it are
  refused when they are made, and funding refuses it as a backstop.

Turning the flag off lifts all three at once; nothing is migrated.
"""

from functools import cache

from django.conf import settings
from django.utils.module_loading import import_string

from apps.flags.services import is_enabled
from apps.gigs.plans import Plan

FLAG = "closed_beta"


class BetaLimitReached(Exception):
    code = "beta_limit"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def active() -> bool:
    return is_enabled(FLAG)


def invite_required(role: str) -> bool:
    return active() and role in settings.BETA_INVITE_ROLES


def live_gig_cap() -> int | None:
    return settings.BETA_MAX_LIVE_GIGS_PER_VENDOR if active() else None


def stipend_cap_paise() -> int | None:
    return settings.BETA_MAX_STIPEND_RUPEES * 100 if active() else None


def live_gig_message(cap: int) -> str:
    return (
        f"During the closed beta, each host can have {cap} live gig"
        f"{'' if cap == 1 else 's'} at a time. Pause or close one first."
    )


def stipend_message() -> str:
    return (
        f"During the closed beta, a booking's stipend can be at most "
        f"₹{settings.BETA_MAX_STIPEND_RUPEES:,}. Lower the stipend or shorten the stay."
    )


def check_stipend(stipend_paise: int | None) -> None:
    """Refuse a stipend over the beta cap. `None` (no stipend) is always fine."""
    cap = stipend_cap_paise()
    if cap is not None and stipend_paise is not None and stipend_paise > cap:
        raise BetaLimitReached(stipend_message())


def check_offer_terms(terms: dict) -> None:
    """Offers carry the stipend and dates; work out the whole stay's stipend."""
    if stipend_cap_paise() is None or terms.get("stipend_amount") in (None, ""):
        return
    from apps.money.escrow import stipend_for

    check_stipend(stipend_for(terms))


def summary() -> dict:
    """What clients show: the public rules (GET /api/v1/beta/)."""
    on = active()
    return {
        "closed_beta": on,
        "invite_required_for": sorted(settings.BETA_INVITE_ROLES) if on else [],
        "max_live_gigs": live_gig_cap(),
        "max_stipend_rupees": settings.BETA_MAX_STIPEND_RUPEES if on else None,
    }


@cache
def _base_policy(path: str):
    return import_string(path)()


class BetaPlanPolicy:
    """settings.GIG_PLAN_POLICY while the beta runs: the plan's limit, or the beta's
    if that is lower."""

    def plan_for(self, vendor) -> Plan:
        plan = _base_policy(settings.BETA_BASE_PLAN_POLICY).plan_for(vendor)
        cap = live_gig_cap()
        if cap is None or (plan.max_live_gigs is not None and plan.max_live_gigs <= cap):
            return plan
        return Plan(name=plan.name, max_live_gigs=cap, note=live_gig_message(cap))
