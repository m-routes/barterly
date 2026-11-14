from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.tests.factories import AdminUserFactory
from apps.common.models import AuditLog
from apps.gigs.constants import TRANSITIONS, Actor, CompensationModel, GigStatus
from apps.gigs.models import Gig
from apps.gigs.plans import Plan
from apps.gigs.services import (
    GigLocked,
    InvalidGigTransition,
    PlanLimitReached,
    close_expired_gigs,
    create_gig,
    on_confirmed_bookings_changed,
    transition,
    update_gig,
)
from apps.gigs.tests.factories import GigFactory, in_days
from apps.properties.tests.factories import PropertyFactory

pytestmark = pytest.mark.django_db
G = GigStatus


def live_gig(**kwargs) -> Gig:
    gig = GigFactory(**kwargs)
    transition(gig.pk, G.IN_REVIEW, actor=Actor.VENDOR, user=gig.vendor)
    return transition(gig.pk, G.LIVE, actor=Actor.ADMIN, user=AdminUserFactory())


def test_submit_review_approve_and_every_change_is_audited():
    gig = GigFactory()
    admin = AdminUserFactory()
    gig = transition(gig.pk, G.IN_REVIEW, actor=Actor.VENDOR, user=gig.vendor)
    assert gig.submitted_at is not None
    gig = transition(gig.pk, G.DRAFT, actor=Actor.ADMIN, user=admin, reason="Add the dorm size.")
    assert gig.status_reason == "Add the dorm size."
    transition(gig.pk, G.IN_REVIEW, actor=Actor.VENDOR, user=gig.vendor)
    gig = transition(gig.pk, G.LIVE, actor=Actor.ADMIN, user=admin)
    assert gig.published_at is not None and gig.status_reason == ""

    rows = AuditLog.objects.filter(object_id=str(gig.pk)).order_by("created_at", "id")
    assert [r.action for r in rows if r.action != "gig.created"] == [
        "gig.in_review",
        "gig.draft",
        "gig.in_review",
        "gig.live",
    ]
    last = rows.last()
    assert last.actor == admin
    assert last.before["status"] == "in_review" and last.after == {
        "status": "live",
        "status_reason": "",
        "by": "admin",
    }


def test_the_table_decides_who_may_move_what():
    gig = GigFactory()
    with pytest.raises(InvalidGigTransition):  # not in the table
        transition(gig.pk, G.LIVE, actor=Actor.ADMIN)
    transition(gig.pk, G.IN_REVIEW, actor=Actor.VENDOR, user=gig.vendor)
    with pytest.raises(InvalidGigTransition, match="Only admin"):  # vendors can't approve
        transition(gig.pk, G.LIVE, actor=Actor.VENDOR, user=gig.vendor)
    gig.refresh_from_db()
    assert gig.status == G.IN_REVIEW
    assert not AuditLog.objects.filter(action="gig.live").exists()


def test_every_status_is_reachable_and_archived_is_final():
    assert {to for (_, to) in TRANSITIONS} == set(G.values)
    assert not [pair for pair in TRANSITIONS if pair[0] == G.ARCHIVED]


def test_submit_checks_the_rules_and_send_back_needs_a_reason():
    gig = GigFactory(hours_per_day=None)
    with pytest.raises(ValidationError):
        transition(gig.pk, G.IN_REVIEW, actor=Actor.VENDOR, user=gig.vendor)
    gig = GigFactory()
    transition(gig.pk, G.IN_REVIEW, actor=Actor.VENDOR, user=gig.vendor)
    with pytest.raises(ValueError):
        transition(gig.pk, G.DRAFT, actor=Actor.ADMIN, user=AdminUserFactory(), reason=" ")
    # The vendor withdrawing needs no reason.
    transition(gig.pk, G.DRAFT, actor=Actor.VENDOR, user=gig.vendor)


class TestEdits:
    def test_pay_hours_or_dates_on_a_live_gig_go_back_to_review(self):
        gig = live_gig()
        gig = update_gig(gig.pk, {"hours_per_day": 4}, user=gig.vendor)
        assert gig.status == G.IN_REVIEW
        assert "hours per day" in gig.status_reason
        entry = AuditLog.objects.filter(action="gig.in_review").latest("created_at")
        assert entry.after["by"] == "system" and entry.actor == gig.vendor

    def test_other_edits_keep_it_live(self):
        gig = live_gig()
        gig = update_gig(
            gig.pk, {"description": "Now with a rooftop cafe.", "wifi": False}, user=gig.vendor
        )
        assert gig.status == G.LIVE

    def test_same_values_are_not_a_change(self):
        gig = live_gig()
        gig = update_gig(gig.pk, {"hours_per_day": gig.hours_per_day}, user=gig.vendor)
        assert gig.status == G.LIVE

    def test_money_changes_are_audited(self):
        gig = GigFactory(
            compensation_model=CompensationModel.HYBRID,
            stipend_amount=Decimal("5000"),
            stipend_period="per_month",
        )
        update_gig(gig.pk, {"stipend_amount": Decimal("6500.00")}, user=gig.vendor)
        entry = AuditLog.objects.get(action="gig.compensation_changed")
        assert (
            entry.before["stipend_amount"] == "5000.00"
            and entry.after["stipend_amount"] == "6500.00"
        )

    def test_edits_past_draft_must_keep_the_gig_valid(self):
        gig = live_gig()
        with pytest.raises(ValidationError):
            update_gig(gig.pk, {"meals": ""}, user=gig.vendor)
        gig.refresh_from_db()
        assert gig.status == G.LIVE and gig.meals

    def test_a_started_live_gig_can_still_fix_its_description(self):
        gig = live_gig()
        Gig.objects.filter(pk=gig.pk).update(start_date=in_days(-1), apply_by=in_days(-3))
        gig = update_gig(gig.pk, {"description": "Typo fixed."}, user=gig.vendor)
        assert gig.status == G.LIVE

    def test_closed_gigs_are_locked(self):
        gig = live_gig()
        transition(gig.pk, G.CLOSED, actor=Actor.VENDOR, user=gig.vendor)
        with pytest.raises(GigLocked):
            update_gig(gig.pk, {"title": "Reopen"}, user=gig.vendor)


def test_create_checks_shape_and_audits():
    prop = PropertyFactory()
    with pytest.raises(ValidationError):
        create_gig(
            prop.vendor,
            {
                "property": prop,
                "title": "x",
                "role_template": "volunteer",
                "compensation_model": "volunteer",
                "hours_per_day": 8,
            },
        )
    gig = create_gig(
        prop.vendor,
        {
            "property": prop,
            "title": "Muralist",
            "role_template": "specialist",
            "compensation_model": "barter",
        },
    )
    assert gig.status == G.DRAFT
    assert AuditLog.objects.filter(action="gig.created", object_id=str(gig.pk)).exists()


class CappedPolicy:
    def plan_for(self, vendor):
        return Plan(name="starter", max_live_gigs=1)


def test_plan_limit_blocks_going_live(settings):
    from apps.gigs import plans

    settings.GIG_PLAN_POLICY = "apps.gigs.tests.test_services.CappedPolicy"
    plans._build.cache_clear()
    try:
        first = live_gig()
        second = GigFactory(property=PropertyFactory(vendor=first.vendor))
        transition(second.pk, G.IN_REVIEW, actor=Actor.VENDOR, user=second.vendor)
        with pytest.raises(PlanLimitReached):
            transition(second.pk, G.LIVE, actor=Actor.ADMIN, user=AdminUserFactory())
        transition(first.pk, G.PAUSED, actor=Actor.VENDOR, user=first.vendor)
        transition(second.pk, G.LIVE, actor=Actor.ADMIN, user=AdminUserFactory())
        with pytest.raises(PlanLimitReached):  # resuming counts too
            transition(first.pk, G.LIVE, actor=Actor.VENDOR, user=first.vendor)
    finally:
        plans._build.cache_clear()


def test_unlimited_plan_by_default():
    vendor_gig = live_gig()
    for _ in range(3):
        live_gig(property=PropertyFactory(vendor=vendor_gig.vendor))
    assert Gig.objects.filter(vendor=vendor_gig.vendor, status=G.LIVE).count() == 4


def test_auto_close_after_apply_by():
    open_gig = live_gig()
    expired = live_gig()
    paused = live_gig()
    transition(paused.pk, G.PAUSED, actor=Actor.VENDOR, user=paused.vendor)
    later = timezone.localdate() + timedelta(days=21)  # past apply_by (20 days)
    Gig.objects.filter(pk=open_gig.pk).update(apply_by=in_days(25), start_date=in_days(30))
    assert close_expired_gigs(today=later) == 2
    statuses = dict(Gig.objects.values_list("pk", "status"))
    assert statuses[expired.pk] == G.CLOSED and statuses[paused.pk] == G.CLOSED
    assert statuses[open_gig.pk] == G.LIVE
    assert AuditLog.objects.filter(action="gig.closed", actor__isnull=True).count() == 2


def test_resuming_after_apply_by_is_refused():
    gig = live_gig()
    transition(gig.pk, G.PAUSED, actor=Actor.VENDOR, user=gig.vendor)
    Gig.objects.filter(pk=gig.pk).update(apply_by=in_days(-1))
    with pytest.raises(ValidationError):
        transition(gig.pk, G.LIVE, actor=Actor.VENDOR, user=gig.vendor)


def test_bookings_hook_fills_and_reopens():
    gig = live_gig()  # 2 slots
    assert on_confirmed_bookings_changed(gig.pk, 1).status == G.LIVE
    assert on_confirmed_bookings_changed(gig.pk, 2).status == G.FILLED
    assert on_confirmed_bookings_changed(gig.pk, 1).status == G.LIVE
    Gig.objects.filter(pk=gig.pk).update(status=G.FILLED, apply_by=in_days(-1))
    assert on_confirmed_bookings_changed(gig.pk, 1).status == G.FILLED  # applications closed
