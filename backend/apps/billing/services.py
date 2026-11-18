"""Subscribing, changing plan, cancelling, gateway webhooks and dunning.

The flow:
1. subscribe(): the gateway makes a subscription and a hosted checkout link; the vendor
   pays there. With a trial (a coupon, or BILLING_LAUNCH_TRIAL_DAYS for the first
   cohort), the card is set up now and the first charge waits until the trial ends.
2. Webhooks keep our copy current (handle_webhook): authenticated (card set up),
   activated, charged (an invoice is issued), pending (a charge failed: the gateway
   retries it), halted (retries used up), cancelled, completed. Each event is handled
   once: its id is recorded, and a repeat delivery does nothing.
3. Dunning: the first failed charge starts a grace period (BILLING_GRACE_DAYS). Paid
   features stay on while the gateway retries; the vendor is told at once, reminded
   before the grace ends, and told when features lock (dunning(), a daily job). A
   successful charge ends it all.

Every status change is audited (billing.subscription_<status>).
"""

import contextlib
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.billing import invoices
from apps.billing.gateway.base import GatewayError, get_gateway
from apps.billing.models import (
    OPEN_STATUSES,
    Coupon,
    Plan,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
)
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action, snapshot

S = SubscriptionStatus
AUDIT_FIELDS = ["status", "plan_id", "grace_until"]


class BillingError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def _grace() -> timedelta:
    return timedelta(days=settings.BILLING_GRACE_DAYS)


def _move(
    subscription: Subscription, status: str, *, now, actor=None, request=None, **changes
) -> None:
    before = snapshot(subscription, AUDIT_FIELDS)
    subscription.status = status
    for field, value in changes.items():
        setattr(subscription, field, value)
    subscription.save()
    log_action(
        actor=actor,
        action=f"billing.subscription_{status}",
        obj=subscription,
        before=before,
        after={**snapshot(subscription, AUDIT_FIELDS), "plan": subscription.plan.code},
        request=request,
    )


def _notify(name: str, subscription: Subscription, *, now, key: str, **extra) -> None:
    publish(
        DomainEvent(
            name,
            {
                "subscription_id": str(subscription.pk),
                "vendor_id": str(subscription.vendor_id),
                "plan_name": subscription.plan.name,
                "checkout_url": subscription.checkout_url,
                "notify": ["vendor"],
                "dedup_key": f"{name}:{subscription.pk}:{key}",
                **extra,
            },
            occurred_at=now,
        )
    )


# ---------- The vendor's moves ----------


def _plan(code: str) -> Plan:
    plan = Plan.objects.filter(code=code, is_public=True).first()
    if plan is None:
        raise BillingError("No such plan.", 400)
    if not plan.gateway_plan_id:
        raise BillingError("This plan isn't on sale yet.", 409)
    return plan


def _trial_days(vendor, coupon: Coupon | None) -> int:
    if coupon is not None:
        return coupon.trial_days
    first_time = not Subscription.objects.filter(vendor=vendor).exclude(status=S.CREATED).exists()
    return settings.BILLING_LAUNCH_TRIAL_DAYS if first_time else 0


def subscribe(vendor, *, plan_code: str, coupon_code: str = "", request=None, now=None):
    """Start a subscription; the vendor finishes at the returned checkout link."""
    now = now or timezone.now()
    plan = _plan(plan_code)
    with transaction.atomic():
        current = (
            Subscription.objects.select_for_update()
            .filter(vendor=vendor, status__in=OPEN_STATUSES)
            .first()
        )
        if current and current.status != S.CREATED:
            raise BillingError("You already have a plan. Change it instead.")
        if current and current.plan_id == plan.pk and not coupon_code:
            return current  # the same checkout, still waiting
        coupon = None
        if coupon_code:
            coupon = Coupon.objects.select_for_update().filter(code__iexact=coupon_code).first()
            if coupon is None or not coupon.usable(now):
                raise BillingError("That code isn't valid.", 400)
        if current:  # an unpaid checkout for another plan: replace it
            # Never paid, so there's nothing to stop if the gateway says no.
            with contextlib.suppress(GatewayError):
                get_gateway().cancel(current.gateway_subscription_id, at_cycle_end=False)
            _move(current, S.CANCELLED, now=now, actor=vendor, request=request, ended_at=now)
        days = _trial_days(vendor, coupon)
        trial_end = now + timedelta(days=days) if days else None
        try:
            created = get_gateway().create_subscription(
                plan_id=plan.gateway_plan_id,
                start_at=trial_end,
                notes={"vendor_id": vendor.pk, "plan": plan.code},
            )
        except GatewayError as exc:
            raise BillingError(str(exc), 502) from exc
        subscription = Subscription.objects.create(
            vendor=vendor,
            plan=plan,
            gateway=get_gateway().name,
            gateway_subscription_id=created.id,
            checkout_url=created.checkout_url,
            coupon=coupon,
            trial_ends_at=trial_end,
            created_at=now,
        )
        if coupon is not None:
            Coupon.objects.filter(pk=coupon.pk).update(redemptions=F("redemptions") + 1)
        log_action(
            actor=vendor,
            action="billing.subscription_created",
            obj=subscription,
            after={
                "plan": plan.code,
                "trial_ends_at": trial_end,
                "coupon": coupon.code if coupon else "",
            },
            request=request,
        )
    return subscription


def change_plan(vendor, *, plan_code: str, request=None, now=None) -> Subscription:
    """Upgrades take effect now (the gateway charges the difference); downgrades at the
    end of the period, so what's paid for isn't lost. Live gigs keep running either
    way; new ones over the new limit are refused (apps.billing.entitlements)."""
    now = now or timezone.now()
    plan = _plan(plan_code)
    with transaction.atomic():
        subscription = (
            Subscription.objects.select_for_update(of=("self",))
            .select_related("plan")
            .filter(vendor=vendor, status__in=(S.AUTHENTICATED, S.ACTIVE))
            .first()
        )
        if subscription is None:
            raise BillingError("You don't have an active plan to change.")
        if subscription.plan_id == plan.pk:
            if subscription.pending_plan_id:  # undo a scheduled downgrade
                get_gateway().change_plan(
                    subscription.gateway_subscription_id,
                    plan_id=plan.gateway_plan_id,
                    at_cycle_end=True,
                )
                subscription.pending_plan = None
                subscription.save(update_fields=["pending_plan", "updated_at"])
            return subscription
        upgrade = plan.price_paise > subscription.plan.price_paise
        try:
            get_gateway().change_plan(
                subscription.gateway_subscription_id,
                plan_id=plan.gateway_plan_id,
                at_cycle_end=not upgrade,
            )
        except GatewayError as exc:
            raise BillingError(str(exc), 502) from exc
        before = {"plan": subscription.plan.code}
        if upgrade:
            subscription.plan = plan
            subscription.pending_plan = None
        else:
            subscription.pending_plan = plan
        subscription.save(update_fields=["plan", "pending_plan", "updated_at"])
        log_action(
            actor=vendor,
            action="billing.plan_upgraded" if upgrade else "billing.downgrade_scheduled",
            obj=subscription,
            before=before,
            after={"plan": plan.code, "at": "now" if upgrade else "period_end"},
            request=request,
        )
    return subscription


def cancel(vendor, *, at_period_end: bool = True, request=None, now=None) -> Subscription:
    now = now or timezone.now()
    with transaction.atomic():
        subscription = (
            Subscription.objects.select_for_update(of=("self",))
            .select_related("plan")
            .filter(vendor=vendor, status__in=OPEN_STATUSES)
            .first()
        )
        if subscription is None:
            raise BillingError("You don't have a plan to cancel.")
        try:
            get_gateway().cancel(subscription.gateway_subscription_id, at_cycle_end=at_period_end)
        except GatewayError as exc:
            raise BillingError(str(exc), 502) from exc
        if at_period_end and subscription.status in (S.AUTHENTICATED, S.ACTIVE):
            subscription.cancel_at_period_end = True
            subscription.save(update_fields=["cancel_at_period_end", "updated_at"])
            log_action(
                actor=vendor,
                action="billing.cancel_scheduled",
                obj=subscription,
                after={"at": subscription.current_period_end},
                request=request,
            )
        else:
            _move(subscription, S.CANCELLED, now=now, actor=vendor, request=request, ended_at=now)
    return subscription


# ---------- Webhooks ----------


def _ts(value) -> datetime | None:
    return datetime.fromtimestamp(int(value), tz=UTC) if value else None


def handle_webhook(body: bytes, headers, now=None) -> str:
    """Verify, record once, and apply. Returns what happened (for the log)."""
    now = now or timezone.now()
    gateway = get_gateway()
    event = gateway.parse_webhook(body, headers)  # raises GatewayError on a bad signature
    try:
        with transaction.atomic():
            record = WebhookEvent.objects.create(
                gateway=gateway.name,
                event_id=event.event_id,
                event=event.event,
                payload=event.raw,
                received_at=now,
            )
    except IntegrityError:
        return "duplicate"
    with transaction.atomic():
        outcome = _apply(event, now=now)
        WebhookEvent.objects.filter(pk=record.pk).update(processed_at=now, outcome=outcome)
    return outcome


def _apply(event, *, now) -> str:
    sub_id = event.subscription.get("id")
    if not sub_id:
        return "ignored: no subscription"
    subscription = (
        Subscription.objects.select_for_update(of=("self",))
        .select_related("plan", "pending_plan", "vendor__vendor_profile")
        .filter(gateway_subscription_id=sub_id)
        .first()
    )
    if subscription is None:
        return "ignored: unknown subscription"
    entity = event.subscription
    period = {
        "current_period_start": _ts(entity.get("current_start")),
        "current_period_end": _ts(entity.get("current_end")),
    }
    period = {k: v for k, v in period.items() if v}
    name = event.event

    if name == "subscription.authenticated":
        if subscription.status == S.CREATED:
            _move(subscription, S.AUTHENTICATED, now=now, **period)
        return "authenticated"
    if name == "subscription.activated":
        if subscription.status in (S.CREATED, S.AUTHENTICATED, S.PAST_DUE, S.HALTED):
            _move(subscription, S.ACTIVE, now=now, **period, **_cleared())
        return "activated"
    if name == "subscription.charged":
        changes = {**period, **_cleared()}
        if subscription.pending_plan_id and (
            entity.get("plan_id") == subscription.pending_plan.gateway_plan_id
        ):
            changes.update(plan=subscription.pending_plan, pending_plan=None)
        _move(subscription, S.ACTIVE, now=now, **changes)
        payment = event.payment
        if payment.get("id"):
            invoices.issue(
                subscription,
                payment_id=payment["id"],
                amount_paise=int(payment.get("amount") or 0),
                now=now,
                period_start=subscription.current_period_start,
                period_end=subscription.current_period_end,
            )
        return "charged"
    if name == "subscription.pending":
        failed = subscription.payment_failed_at or now
        first = subscription.payment_failed_at is None
        _move(
            subscription,
            S.PAST_DUE,
            now=now,
            payment_failed_at=failed,
            grace_until=subscription.grace_until or failed + _grace(),
        )
        if first:
            _notify(
                "billing.payment_failed",
                subscription,
                now=now,
                key=failed.isoformat(),
                grace_until=subscription.grace_until,
            )
        return "past due"
    if name == "subscription.halted":
        failed = subscription.payment_failed_at or now
        _move(
            subscription,
            S.HALTED,
            now=now,
            payment_failed_at=failed,
            grace_until=subscription.grace_until or failed + _grace(),
        )
        return "halted"
    if name in ("subscription.cancelled", "subscription.completed"):
        status = S.CANCELLED if name.endswith("cancelled") else S.COMPLETED
        if subscription.status not in (S.CANCELLED, S.COMPLETED):
            _move(subscription, status, now=now, ended_at=now)
        return status
    return f"ignored: {name}"


def _cleared() -> dict:
    return {"payment_failed_at": None, "grace_until": None, "reminders_sent": 0}


# ---------- Dunning ----------

REMIND_BEFORE = timedelta(days=2)


def dunning(now) -> dict[str, int]:
    """Job: remind vendors whose grace period is ending, and tell those whose paid
    features just locked. Each message goes once per dunning run."""
    reminded = locked = 0
    late = Subscription.objects.select_related("plan").filter(
        status__in=(S.PAST_DUE, S.HALTED), grace_until__isnull=False
    )
    for subscription in late:
        key = subscription.payment_failed_at.isoformat()
        if subscription.grace_until <= now and subscription.reminders_sent < 2:
            _notify("billing.features_locked", subscription, now=now, key=key)
            log_action(
                actor=None,
                action="billing.features_locked",
                obj=subscription,
                after={"grace_until": subscription.grace_until, "plan": subscription.plan.code},
            )
            Subscription.objects.filter(pk=subscription.pk).update(reminders_sent=2)
            locked += 1
        elif (
            subscription.grace_until - now <= REMIND_BEFORE
            and subscription.grace_until > now
            and subscription.reminders_sent < 1
        ):
            _notify(
                "billing.grace_ending",
                subscription,
                now=now,
                key=key,
                grace_until=subscription.grace_until,
            )
            Subscription.objects.filter(pk=subscription.pk).update(reminders_sent=1)
            reminded += 1
    return {"reminded": reminded, "locked": locked}
