"""What a vendor's plan lets them do.

- current_plan(vendor): the plan in effect. A subscription counts while it's in a trial,
  active, or past due inside its grace period. Otherwise the vendor is on FREE.
- can_post_gig(vendor): whether one more gig may go live (the plan's live gig limit).
  A downgrade never takes gigs down: ones already live keep running, and new ones are
  refused until the vendor is under the new limit.
- can_use_feature(vendor, flag): one of models.FEATURES.

BillingPlanPolicy plugs this into gigs (settings.GIG_PLAN_POLICY), replacing the
unlimited stub from Phase 2.
"""

from dataclasses import dataclass

from django.utils import timezone

from apps.billing.models import FEATURES, Plan, Subscription, SubscriptionStatus
from apps.gigs import plans as gig_plans

# No subscription (or one that has lapsed): one live gig and no paid features.
FREE = Plan(
    code="free",
    name="Free",
    price_paise=0,
    max_live_gigs=1,
    features={"agreements": True},
)

GIVES_ACCESS = (SubscriptionStatus.AUTHENTICATED, SubscriptionStatus.ACTIVE)


def current_subscription(vendor) -> Subscription | None:
    return (
        Subscription.objects.select_related("plan")
        .filter(vendor=vendor)
        .exclude(status__in=(SubscriptionStatus.CANCELLED, SubscriptionStatus.COMPLETED))
        .order_by("-created_at")
        .first()
    )


def in_effect(subscription: Subscription | None, now=None) -> bool:
    if subscription is None:
        return False
    now = now or timezone.now()
    if subscription.status in GIVES_ACCESS:
        return True
    if subscription.status in (SubscriptionStatus.PAST_DUE, SubscriptionStatus.HALTED):
        # A failed charge: paid features stay on until the grace period ends.
        return subscription.grace_until is not None and subscription.grace_until > now
    return False


def current_plan(vendor, now=None) -> Plan:
    subscription = current_subscription(vendor)
    return subscription.plan if in_effect(subscription, now) else FREE


def live_gig_count(vendor) -> int:
    from apps.gigs.constants import GigStatus
    from apps.gigs.models import Gig

    return Gig.objects.filter(vendor=vendor, status=GigStatus.LIVE).count()


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    limit: int | None = None
    used: int = 0


def can_post_gig(vendor, now=None) -> Decision:
    plan = current_plan(vendor, now)
    used = live_gig_count(vendor)
    if plan.max_live_gigs is None or used < plan.max_live_gigs:
        return Decision(True, limit=plan.max_live_gigs, used=used)
    return Decision(
        False,
        reason=(
            f"Your {plan.name} plan allows {plan.max_live_gigs} live gig"
            f"{'' if plan.max_live_gigs == 1 else 's'}. Pause one, or upgrade, to go live."
        ),
        limit=plan.max_live_gigs,
        used=used,
    )


def can_use_feature(vendor, flag: str, now=None) -> bool:
    if flag not in FEATURES:
        raise ValueError(f"Unknown feature {flag!r}; one of {', '.join(FEATURES)}.")
    return current_plan(vendor, now).has(flag)


def summary(vendor, now=None) -> dict:
    """Everything the console shows about what the vendor can do."""
    plan = current_plan(vendor, now)
    gigs = can_post_gig(vendor, now)
    return {
        "plan": plan.code,
        "plan_name": plan.name,
        "max_live_gigs": plan.max_live_gigs,
        "live_gigs": gigs.used,
        "can_post_gig": gigs.allowed,
        "reason": gigs.reason,
        "features": {flag: plan.has(flag) for flag in FEATURES},
    }


class BillingPlanPolicy:
    """settings.GIG_PLAN_POLICY: gigs ask here how many may be live."""

    def plan_for(self, vendor) -> gig_plans.Plan:
        plan = current_plan(vendor)
        return gig_plans.Plan(name=plan.name, max_live_gigs=plan.max_live_gigs)
