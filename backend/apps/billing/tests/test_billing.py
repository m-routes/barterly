"""Subscribing, webhooks, dunning, entitlements and the API."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing import entitlements, services
from apps.billing.gateway.base import GatewayError
from apps.billing.gateway.fake import FakeGateway
from apps.billing.models import Coupon, Invoice, Subscription, WebhookEvent
from apps.billing.tests.helpers import plans_on_sale, ts, vendor, webhook
from apps.common.models import AuditLog
from apps.gigs.constants import GigStatus
from apps.gigs.models import Gig
from apps.gigs.tests.factories import GigFactory
from apps.notifications.models import Notification
from apps.properties.tests.factories import PropertyFactory
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def plans():
    return plans_on_sale()


def active(owner, plan, **extra) -> Subscription:
    return Subscription.objects.create(
        vendor=owner,
        plan=plan,
        status="active",
        gateway_subscription_id=f"sub_{owner.pk}",
        **extra,
    )


def deliver(event, sub, event_id, **kw):
    return services.handle_webhook(*webhook(event, sub.gateway_subscription_id, event_id, **kw))


class TestSubscribing:
    def test_starts_at_the_hosted_checkout(self, plans):
        owner = vendor()
        sub = services.subscribe(owner, plan_code="growth")
        assert sub.status == "created" and sub.checkout_url.startswith("https://rzp.test/")
        assert FakeGateway.calls[0][:3] == ("create", "plan_growth", None)
        assert AuditLog.objects.filter(action="billing.subscription_created").exists()
        # Asking again while the checkout is still open returns the same one.
        assert services.subscribe(owner, plan_code="growth").pk == sub.pk

    def test_a_coupon_gives_the_trial_and_counts_once(self, plans):
        Coupon.objects.create(code="FIRST100", trial_days=90, max_redemptions=1)
        now = timezone.now()
        sub = services.subscribe(vendor(), plan_code="starter", coupon_code="first100", now=now)
        assert sub.trial_ends_at == now + timedelta(days=90)
        assert FakeGateway.calls[-1][2] == now + timedelta(days=90)  # first charge waits
        assert Coupon.objects.get().redemptions == 1
        with pytest.raises(services.BillingError, match="isn't valid"):
            services.subscribe(vendor(), plan_code="starter", coupon_code="FIRST100")

    def test_the_launch_trial_is_for_first_subscriptions(self, plans, settings):
        settings.BILLING_LAUNCH_TRIAL_DAYS = 90
        owner = vendor()
        assert services.subscribe(owner, plan_code="growth").trial_ends_at is not None
        Subscription.objects.filter(vendor=owner).update(status="cancelled")
        Subscription.objects.create(
            vendor=owner, plan=plans["growth"], status="completed", gateway_subscription_id="x"
        )
        assert services.subscribe(owner, plan_code="pro").trial_ends_at is None

    def test_refusals(self, plans):
        owner = vendor()
        active(owner, plans["starter"])
        with pytest.raises(services.BillingError, match="Change it instead"):
            services.subscribe(owner, plan_code="growth")
        with pytest.raises(services.BillingError, match="No such plan"):
            services.subscribe(vendor(), plan_code="enterprise")
        plans["pro"].gateway_plan_id = ""
        plans["pro"].save()
        with pytest.raises(services.BillingError, match="isn't on sale"):
            services.subscribe(vendor(), plan_code="pro")
        FakeGateway.fail_next = [GatewayError("The payment provider said: bad plan")]
        with pytest.raises(services.BillingError, match="bad plan") as caught:
            services.subscribe(vendor(), plan_code="growth")
        assert caught.value.status == 502

    def test_choosing_another_plan_replaces_an_unpaid_checkout(self, plans):
        owner = vendor()
        first = services.subscribe(owner, plan_code="starter")
        second = services.subscribe(owner, plan_code="growth")
        first.refresh_from_db()
        assert first.status == "cancelled" and second.status == "created"
        assert ("cancel", first.gateway_subscription_id, False) in FakeGateway.calls


class TestChangingPlan:
    def test_upgrades_now_and_downgrades_at_the_period_end(self, plans):
        owner = vendor()
        sub = active(owner, plans["growth"])
        services.change_plan(owner, plan_code="pro")
        sub.refresh_from_db()
        assert sub.plan.code == "pro" and FakeGateway.calls[-1][-1] is False
        services.change_plan(owner, plan_code="starter")
        sub.refresh_from_db()
        assert sub.plan.code == "pro" and sub.pending_plan.code == "starter"
        assert FakeGateway.calls[-1] == (
            "change",
            sub.gateway_subscription_id,
            "plan_starter",
            True,
        )
        assert AuditLog.objects.filter(action="billing.downgrade_scheduled").exists()

    def test_a_downgrade_keeps_live_gigs_running_but_blocks_new_ones(self, plans):
        owner = vendor()
        prop = PropertyFactory(vendor=owner)
        sub = active(owner, plans["growth"])
        for _ in range(3):
            GigFactory(property=prop, status=GigStatus.LIVE)
        assert entitlements.can_post_gig(owner).allowed
        sub.plan = plans["starter"]
        sub.save()
        decision = entitlements.can_post_gig(owner)
        assert not decision.allowed and (decision.used, decision.limit) == (3, 1)
        assert "Starter plan allows 1 live gig" in decision.reason
        assert Gig.objects.filter(vendor=owner, status=GigStatus.LIVE).count() == 3

    def test_cancelling(self, plans):
        owner = vendor()
        sub = active(owner, plans["growth"])
        services.cancel(owner)
        sub.refresh_from_db()
        assert sub.cancel_at_period_end and sub.status == "active"
        services.cancel(owner, at_period_end=False)
        sub.refresh_from_db()
        assert sub.status == "cancelled"
        with pytest.raises(services.BillingError):
            services.change_plan(owner, plan_code="pro")


class TestWebhooks:
    def test_a_bad_signature_is_refused(self, plans):
        body, headers = webhook("subscription.activated", "sub_x", "evt_1")
        headers["X-Razorpay-Signature"] = "0" * 64
        with pytest.raises(GatewayError, match="signature"):
            services.handle_webhook(body, headers)
        assert not WebhookEvent.objects.exists()

    def test_the_lifecycle_and_each_event_once(self, plans, django_capture_on_commit_callbacks):
        owner = vendor()
        sub = services.subscribe(owner, plan_code="growth")
        assert entitlements.current_plan(owner).code == "free"

        assert deliver("subscription.authenticated", sub, "evt_1") == "authenticated"
        start, end = timezone.now(), timezone.now() + timedelta(days=30)
        with django_capture_on_commit_callbacks(execute=True):
            outcome = deliver(
                "subscription.charged",
                sub,
                "evt_2",
                payment={"id": "pay_1", "amount": 294882, "status": "captured"},
                current_start=ts(start),
                current_end=ts(end),
                plan_id="plan_growth",
            )
        assert outcome == "charged"
        assert deliver("subscription.charged", sub, "evt_2") == "duplicate"
        sub.refresh_from_db()
        assert sub.status == "active" and sub.current_period_end is not None
        assert Invoice.objects.filter(gateway_payment_id="pay_1").count() == 1
        assert entitlements.current_plan(owner).code == "growth"
        assert AuditLog.objects.filter(action="billing.subscription_active").exists()

        assert deliver("subscription.cancelled", sub, "evt_3") == "cancelled"
        assert entitlements.current_plan(owner).code == "free"

    def test_a_downgrade_lands_with_the_next_charge(self, plans):
        owner = vendor()
        sub = active(owner, plans["pro"], pending_plan=plans["starter"])
        deliver(
            "subscription.charged",
            sub,
            "evt_9",
            payment={"id": "pay_9", "amount": 117882},
            plan_id="plan_starter",
        )
        sub.refresh_from_db()
        assert sub.plan.code == "starter" and sub.pending_plan is None

    def test_unknown_subscriptions_are_recorded_and_ignored(self, plans):
        body, headers = webhook("subscription.activated", "sub_nobody", "evt_5")
        assert services.handle_webhook(body, headers) == "ignored: unknown subscription"
        assert WebhookEvent.objects.get().outcome == "ignored: unknown subscription"


class TestDunning:
    def test_failure_grace_reminder_lock_and_recovery(self, plans, settings):
        settings.BILLING_GRACE_DAYS = 7
        owner = vendor()
        sub = active(owner, plans["growth"])
        failed_at = timezone.now()

        services.handle_webhook(
            *webhook("subscription.pending", sub.gateway_subscription_id, "evt_p1"),
            now=failed_at,
        )
        sub.refresh_from_db()
        assert sub.status == "past_due" and sub.grace_until == failed_at + timedelta(days=7)
        assert Notification.objects.filter(user=owner, kind="billing.payment_failed").count() == 1
        # The gateway retries; features stay on through the grace period.
        assert entitlements.current_plan(owner, failed_at + timedelta(days=6)).code == "growth"
        assert entitlements.can_use_feature(owner, "talent_search", failed_at)

        # Halted inside the grace period: still on until it ends.
        services.handle_webhook(
            *webhook("subscription.halted", sub.gateway_subscription_id, "evt_h1"),
            now=failed_at + timedelta(days=4),
        )
        assert entitlements.current_plan(owner, failed_at + timedelta(days=5)).code == "growth"

        assert services.dunning(failed_at + timedelta(days=3)) == {"reminded": 0, "locked": 0}
        assert services.dunning(failed_at + timedelta(days=6)) == {"reminded": 1, "locked": 0}
        assert services.dunning(failed_at + timedelta(days=6, hours=1))["reminded"] == 0
        assert services.dunning(failed_at + timedelta(days=8)) == {"reminded": 0, "locked": 1}
        assert services.dunning(failed_at + timedelta(days=9))["locked"] == 0
        kinds = set(Notification.objects.filter(user=owner).values_list("kind", flat=True))
        assert {"billing.grace_ending", "billing.features_locked"} <= kinds
        locked = failed_at + timedelta(days=8)
        assert entitlements.current_plan(owner, locked).code == "free"
        assert not entitlements.can_use_feature(owner, "talent_search", locked)

        # A charge that goes through ends it.
        services.handle_webhook(
            *webhook(
                "subscription.charged",
                sub.gateway_subscription_id,
                "evt_c2",
                payment={"id": "pay_2", "amount": 294882},
            ),
            now=locked,
        )
        sub.refresh_from_db()
        assert (sub.status, sub.grace_until, sub.payment_failed_at) == ("active", None, None)

    def test_the_job_is_registered(self):
        from apps.bookings import jobs

        assert {"billing_dunning", "billing_invoices"} <= set(jobs.JOBS)


class TestEntitlements:
    def test_free_by_default_and_plans_unlock_features(self, plans):
        owner = vendor()
        assert entitlements.current_plan(owner).code == "free"
        assert entitlements.can_use_feature(owner, "agreements")
        assert not entitlements.can_use_feature(owner, "ai_fit_scores")
        active(owner, plans["pro"])
        assert entitlements.can_use_feature(owner, "team_roles")
        assert entitlements.can_post_gig(owner).limit is None
        with pytest.raises(ValueError, match="Unknown feature"):
            entitlements.can_use_feature(owner, "time_travel")

    def test_gigs_go_live_within_the_plan(self, plans):
        from apps.accounts.tests.factories import AdminUserFactory
        from apps.gigs.services import Actor as GigActor
        from apps.gigs.services import PlanLimitReached, transition

        owner = vendor()
        prop = PropertyFactory(vendor=owner)
        active(owner, plans["starter"])
        GigFactory(property=prop, status=GigStatus.LIVE)
        second = GigFactory(property=prop)
        transition(second.pk, GigStatus.IN_REVIEW, actor=GigActor.VENDOR, user=owner)
        with pytest.raises(PlanLimitReached, match="Starter plan allows 1 live gig"):
            transition(second.pk, GigStatus.LIVE, actor=GigActor.ADMIN, user=AdminUserFactory())


class TestApi:
    def test_plans_overview_and_subscribing(self, plans):
        owner = vendor()
        api = client_for(owner)
        listed = api.get("/api/v1/billing/plans/").json()
        assert [p["code"] for p in listed] == ["starter", "growth", "pro"]
        assert listed[1]["features"]["ai_fit_scores"] is True
        assert listed[0]["gst_percent"] == 18.0
        overview = api.get("/api/v1/billing/").json()
        assert overview["subscription"] is None
        assert overview["entitlements"]["plan"] == "free"
        created = api.post("/api/v1/billing/subscribe/", {"plan": "growth"}, format="json")
        assert created.status_code == 201, created.json()
        assert created.json()["checkout_url"].startswith("https://rzp.test/")
        bad = api.post("/api/v1/billing/subscribe/", {"plan": "nope"}, format="json")
        assert bad.status_code == 400
        assert client_for(None).get("/api/v1/billing/").status_code == 401

    def test_invoices_and_their_pdfs_are_the_vendors_own(self, plans):
        from apps.billing import invoices

        owner = vendor()
        sub = active(owner, plans["growth"])
        invoice = invoices.issue(sub, payment_id="pay_a", amount_paise=294882)
        invoices.render(invoice.pk)
        api = client_for(owner)
        rows = api.get("/api/v1/billing/invoices/").json()["results"]
        assert [r["number"] for r in rows] == [invoice.number]
        assert rows[0]["tax_paise"] == invoice.tax_paise and rows[0]["pdf_ready"] is True
        link = api.get(f"/api/v1/billing/invoices/{invoice.pk}/pdf/").json()
        assert link["url"] and link["expires_in"] == 600
        other = client_for(vendor())
        assert other.get(f"/api/v1/billing/invoices/{invoice.pk}/pdf/").status_code == 404

    def test_the_webhook_endpoint(self, plans, client):
        sub = active(vendor(), plans["growth"])
        body, headers = webhook("subscription.activated", sub.gateway_subscription_id, "evt_w")
        post = lambda b, h: client.post(  # noqa: E731
            "/api/v1/billing/webhooks/razorpay/",
            b,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=h["X-Razorpay-Signature"],
            HTTP_X_RAZORPAY_EVENT_ID=h["X-Razorpay-Event-Id"],
        )
        ok = post(body, headers)
        assert ok.status_code == 200 and ok.json() == {"outcome": "activated"}
        assert post(body, headers).json() == {"outcome": "duplicate"}
        assert post(body, {**headers, "X-Razorpay-Signature": "bad"}).status_code == 400

    def test_ai_fit_breakdowns_need_the_feature(self, plans):
        from apps.applications.services import apply
        from apps.applications.tests.helpers import dates, eligible_talent, live_gig

        gig = live_gig()
        apply(eligible_talent(), gig.pk, pitch="Hi", answers=[], attachments=[], **dates())
        api = client_for(gig.vendor)
        row = api.get(f"/api/v1/gigs/{gig.pk}/applications/").json()["results"][0]
        assert row["fit"]["breakdown"] == {} and row["fit"]["score"] >= 0
        active(gig.vendor, plans["growth"])
        row = api.get(f"/api/v1/gigs/{gig.pk}/applications/").json()["results"][0]
        assert row["fit"]["breakdown"]
