from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import AdminUserFactory, UserFactory
from apps.applications.tests.helpers import live_gig
from apps.beta import invites, review, rules
from apps.beta.models import InviteCode, InviteRedemption, ReviewKind, SafetyReview
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.common.models import AuditLog
from apps.flags.services import set_flag
from apps.gigs.constants import GigStatus
from apps.gigs.models import Gig
from apps.gigs.services import PlanLimitReached
from apps.gigs.services import transition as gig_transition
from apps.gigs.tests.factories import GigFactory
from apps.money import escrow
from apps.money.tests.helpers import ensure_accounts, paid_booking
from apps.offers.services import OfferError

pytestmark = pytest.mark.django_db

ROLE = reverse("accounts:me-role")
SIGN_UP = {
    "confirm_adult": True,
    "terms_version": "2026-11-draft-1",
    "privacy_version": "2026-11-draft-1",
}


@pytest.fixture
def beta_on():
    set_flag("closed_beta", True, actor=None, reason="beta opens")


@pytest.fixture
def ops():
    return AdminUserFactory(roles=["ops"])


def newcomer() -> APIClient:
    user = UserFactory(role="")
    api = APIClient()
    api.force_authenticate(user)
    api.user = user
    return api


def code(**kwargs) -> InviteCode:
    [invite] = invites.generate(count=1, cohort=kwargs.pop("cohort", "wave-1"), **kwargs)
    return invite


class TestInvites:
    def test_codes_are_unambiguous_and_typed_any_way(self):
        made = invites.generate(count=20, cohort="wave-1", role="vendor")
        for invite in made:
            assert len(invite.code) == 8
            assert not set(invite.code) & set("01ILO")
        assert invites.normalise(" abcd-2345 ") == "ABCD2345"

    def test_a_batch_per_property_is_labelled_and_audited(self, ops):
        made = invites.generate(
            count=0,
            labels=["Riverbend Hostel, Manali", "Saltwater Café, Goa"],
            cohort="wave-1",
            by=ops,
        )
        assert [i.label for i in made] == ["Riverbend Hostel, Manali", "Saltwater Café, Goa"]
        entry = AuditLog.objects.get(action="beta.invites_created")
        assert entry.actor == ops and entry.after["count"] == 2

    def test_sign_up_is_open_while_the_beta_flag_is_off(self):
        api = newcomer()
        assert api.post(ROLE, {"role": "talent", **SIGN_UP}, format="json").status_code == 200

    def test_sign_up_needs_a_code_during_the_beta(self, beta_on):
        api = newcomer()
        response = api.post(ROLE, {"role": "talent", **SIGN_UP}, format="json")
        assert response.status_code == 403
        assert response.json()["code"] == "invite_required"
        api.user.refresh_from_db()
        assert api.user.role == ""  # nothing half-done

    def test_a_good_code_signs_up_once_and_is_recorded(self, beta_on):
        invite = code(role="vendor")
        api = newcomer()
        response = api.post(
            ROLE,
            {"role": "vendor", **SIGN_UP, "invite_code": invite.display.lower()},
            format="json",
        )
        assert response.status_code == 200, response.json()
        invite.refresh_from_db()
        assert invite.used == 1
        assert InviteRedemption.objects.get(user=api.user).invite == invite
        assert AuditLog.objects.filter(action="beta.invite_redeemed").exists()

        again = newcomer().post(
            ROLE, {"role": "vendor", **SIGN_UP, "invite_code": invite.code}, format="json"
        )
        assert again.status_code == 400
        assert again.json()["code"] == "invite_invalid"
        assert "already been used" in again.json()["message"]

    @pytest.mark.parametrize(
        ("setup", "message"),
        [
            (lambda i: setattr(i, "revoked_at", timezone.now()), "withdrawn"),
            (lambda i: setattr(i, "expires_at", timezone.now() - timedelta(days=1)), "expired"),
            (lambda i: setattr(i, "role", "vendor"), "for hosts"),
        ],
    )
    def test_unusable_codes_say_why(self, beta_on, setup, message):
        invite = code()
        setup(invite)
        invite.save()
        api = newcomer()
        response = api.post(
            ROLE, {"role": "talent", **SIGN_UP, "invite_code": invite.code}, format="json"
        )
        assert response.status_code == 400
        assert message in response.json()["message"]
        invite.refresh_from_db()
        assert invite.used == 0

    def test_a_wrong_code(self, beta_on):
        response = newcomer().post(
            ROLE, {"role": "talent", **SIGN_UP, "invite_code": "ZZZZ-ZZZZ"}, format="json"
        )
        assert response.json()["code"] == "invite_invalid"

    def test_only_listed_roles_need_codes(self, beta_on, settings):
        settings.BETA_INVITE_ROLES = ["vendor"]
        assert (
            newcomer().post(ROLE, {"role": "talent", **SIGN_UP}, format="json").status_code == 200
        )

    def test_the_public_rules(self, beta_on):
        body = APIClient().get(reverse("beta:rules")).json()
        assert body == {
            "closed_beta": True,
            "invite_required_for": ["talent", "vendor"],
            "max_live_gigs": 2,
            "max_stipend_rupees": 20000,
        }


@pytest.fixture
def unlimited_plan(monkeypatch):
    """Hosts on a plan with no live-gig limit, so the beta's cap is the one that bites."""
    from types import SimpleNamespace

    plan = SimpleNamespace(name="Pro", code="pro", max_live_gigs=None, has=lambda flag: True)
    monkeypatch.setattr("apps.billing.entitlements.current_plan", lambda vendor, now=None: plan)


class TestLiveGigCap:
    def test_a_host_can_have_only_the_beta_number_live(self, beta_on, unlimited_plan):
        first = live_gig()
        vendor = first.vendor
        GigFactory(vendor=vendor, property=first.property, status=GigStatus.LIVE)
        third = GigFactory(vendor=vendor, property=first.property, status=GigStatus.IN_REVIEW)
        with pytest.raises(PlanLimitReached, match="closed beta"):
            gig_transition(third.pk, GigStatus.LIVE, actor="admin", user=AdminUserFactory())
        assert Gig.objects.get(pk=third.pk).status == GigStatus.IN_REVIEW

    def test_the_console_says_so_too(self, beta_on, unlimited_plan):
        from apps.billing.entitlements import can_post_gig

        first = live_gig()
        GigFactory(vendor=first.vendor, property=first.property, status=GigStatus.LIVE)
        decision = can_post_gig(first.vendor)
        assert not decision.allowed
        assert decision.limit == 2
        assert "closed beta" in decision.reason

    def test_without_the_beta_the_plan_decides(self):
        assert rules.live_gig_cap() is None


class TestStipendCap:
    def test_an_offer_above_the_cap_is_refused(self, beta_on, settings):
        from apps.bookings.tests.helpers import offered

        settings.BETA_MAX_STIPEND_RUPEES = 1000
        gig = live_gig(compensation_model="paid", stipend_amount=5000, stipend_period="total")
        with pytest.raises(OfferError, match="closed beta") as caught:
            offered(gig)
        assert caught.value.status == 422

    def test_an_offer_within_it_goes_through(self, beta_on):
        from apps.bookings.tests.helpers import offered

        gig = live_gig(compensation_model="paid", stipend_amount=5000, stipend_period="total")
        assert offered(gig).status == "offered"

    def test_funding_refuses_it_as_a_backstop(self, settings):
        ensure_accounts()
        booking = paid_booking()  # offered before the beta's limit applied
        set_flag("closed_beta", True, actor=None, reason="beta opens")
        cache.clear()  # the flag cache clears on commit, which a test never reaches
        settings.BETA_MAX_STIPEND_RUPEES = 1000
        with pytest.raises(escrow.EscrowError, match="closed beta"):
            escrow.start_funding(booking.pk, vendor=booking.vendor)


class TestWeeklyReview:
    def test_disputes_and_reports_are_listed_and_marked_reviewed(self, ops):
        from apps.bookings.models import BookingEvent
        from apps.bookings.tests.helpers import booked

        booking = booked()
        BookingEvent.objects.create(
            booking=booking,
            from_state=BookingStatus.DELIVERING,
            to_state=BookingStatus.DISPUTED,
            actor=Actor.TALENT,
            actor_user=booking.talent,
            reason="Asked to work double hours.",
        )
        week = review.this_week()
        items = review.items_for(week)
        assert [(i.kind, i.object_id) for i in items] == [(ReviewKind.DISPUTE, str(booking.pk))]
        trust = AdminUserFactory(roles=["trust"])
        browser = Client()
        browser.force_login(trust)
        page = browser.get(reverse("admin:beta_safety_review"))
        assert page.status_code == 200
        assert b"Asked to work double hours." in page.content
        saved = browser.post(
            reverse("admin:beta_safety_review"),
            {
                "kind": "dispute",
                "object_id": str(booking.pk),
                "outcome": "action_taken",
                "notes": "Called both; hours agreed in writing.",
                "week": week.isoformat(),
            },
        )
        assert saved.status_code == 302
        assert SafetyReview.objects.get(object_id=str(booking.pk)).reviewed_by == trust
        assert AuditLog.objects.filter(action="beta.safety_reviewed").exists()

    def test_unreviewed_items_from_past_weeks_are_overdue(self):
        from apps.bookings.tests.helpers import offered
        from apps.chat.models import Conversation, Message, MessageReport

        application = offered()
        conversation = Conversation.objects.create(
            application=application,
            talent=application.talent,
            vendor=application.gig.vendor,
            opened_by="vendor_message",
        )
        message = Message.objects.create(
            conversation=conversation, seq=1, sender=application.gig.vendor, body="Come alone."
        )
        report = MessageReport.objects.create(
            message=message, reporter=UserFactory(), reason="harassment", note="Threats."
        )
        MessageReport.objects.filter(pk=report.pk).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        assert [i.object_id for i in review.overdue()] == [str(report.pk)]
        review.record(
            ReviewKind.CHAT_REPORT,
            str(report.pk),
            outcome="action_taken",
            notes="Account suspended.",
            by=AdminUserFactory(),
            week=review.this_week() - timedelta(weeks=1),
        )
        assert review.overdue() == []

    def test_an_outcome_other_than_no_action_needs_notes(self):
        with pytest.raises(ValueError, match="Say what was done"):
            review.record(
                ReviewKind.DISPUTE,
                "x",
                outcome="escalated",
                notes=" ",
                by=AdminUserFactory(),
                week=review.this_week(),
            )


class TestBackOffice:
    def test_ops_make_codes_and_download_them(self, ops):
        browser = Client()
        browser.force_login(ops)
        made = browser.post(
            reverse("admin:beta_invite_batch"),
            {
                "cohort": "wave-1",
                "role": "vendor",
                "labels": "Riverbend Hostel, Manali\nSaltwater Café, Goa\n",
                "max_uses": 1,
                "expires_in_days": 30,
            },
        )
        assert made.status_code == 200
        assert InviteCode.objects.filter(cohort="wave-1").count() == 2
        csv = browser.get(reverse("admin:beta_invite_csv", args=["wave-1"]))
        assert csv.status_code == 200
        assert "Riverbend Hostel" in csv.content.decode()
        assert AuditLog.objects.filter(action="beta.invites_exported").exists()

    def test_the_onboarding_tracker_follows_each_property(self, ops, beta_on):
        invite = code(role="vendor", labels=["Riverbend Hostel, Manali"])
        gig = live_gig()
        InviteRedemption.objects.create(invite=invite, user=gig.vendor, role="vendor")
        browser = Client()
        browser.force_login(ops)
        page = browser.get(reverse("admin:beta_onboarding"), {"cohort": "wave-1"})
        assert page.status_code == 200
        assert b"Riverbend Hostel" in page.content
        from apps.beta import onboarding

        [row] = onboarding.rows_for("wave-1")
        assert row.done["gig_live"] and row.done["property"]

    def test_support_cant_make_codes(self):
        browser = Client()
        browser.force_login(AdminUserFactory(roles=["support"]))
        assert browser.get(reverse("admin:beta_invite_batch")).status_code == 403


def test_users_are_not_created_by_the_rules_endpoint():
    APIClient().get(reverse("beta:rules"))
    assert not User.objects.exists()
