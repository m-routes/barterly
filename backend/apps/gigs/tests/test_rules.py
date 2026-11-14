from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.gigs.constants import CompensationModel, DeliverableType, StayType
from apps.gigs.rules import check_complete, check_shape
from apps.gigs.tests.factories import GigFactory, in_days
from apps.properties.tests.factories import PropertyFactory

pytestmark = pytest.mark.django_db

REEL = {"type": DeliverableType.INSTAGRAM_REEL, "quantity": 2}


def errors(gig, check=check_complete) -> dict:
    with pytest.raises(ValidationError) as exc:
        check(gig)
    return exc.value.message_dict


def test_all_problems_are_reported_at_once():
    gig = GigFactory.build(property=PropertyFactory(), hours_per_day=9, description="")
    assert {"hours_per_day", "description"} <= set(errors(gig))


def test_a_complete_volunteer_gig_passes():
    check_complete(GigFactory.build(property=PropertyFactory()))


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"hours_per_day": 7}, "hours_per_day"),
        ({"days_per_week": 7}, "days_per_week"),
        ({"slots": 0}, "slots"),
        ({"start_date": in_days(0), "apply_by": in_days(0)}, "start_date"),
        ({"apply_by": in_days(-1)}, "apply_by"),
        ({"apply_by": in_days(40)}, "apply_by"),  # after the start date
        ({"end_date": in_days(10)}, "end_date"),  # before the start
        ({"end_date": None}, "end_date"),  # no end date or duration
        ({"duration_days": 14}, "end_date"),  # both end date and duration
        ({"min_stay_days": 90}, "min_stay_days"),  # longer than the gig
        ({"stay_type": StayType.NONE}, "stay_type"),  # volunteer must have a stay
        ({"meals": ""}, "meals"),
        ({"description": " "}, "description"),
        ({"languages": ["xx"]}, "languages"),
        ({"screening_questions": ["?"] * 6}, "screening_questions"),
    ],
)
def test_each_rule(changes, field):
    gig = GigFactory.build(property=PropertyFactory(), **changes)
    assert field in errors(gig)


def test_barter_needs_a_deliverable():
    gig = GigFactory.build(property=PropertyFactory(), compensation_model=CompensationModel.BARTER)
    assert "deliverables" in errors(gig)
    gig.deliverables = [REEL]
    check_complete(gig)


@pytest.mark.parametrize("model", [CompensationModel.HYBRID, CompensationModel.PAID])
def test_hybrid_and_paid_need_a_stipend_above_zero(model):
    gig = GigFactory.build(property=PropertyFactory(), compensation_model=model)
    assert {"stipend_amount", "stipend_period"} <= set(errors(gig))
    gig.stipend_amount, gig.stipend_period = Decimal("0"), "per_month"
    assert "stipend_amount" in errors(gig)
    gig.stipend_amount = Decimal("8000")
    check_complete(gig)


def test_stipend_and_deliverables_only_where_they_belong():
    gig = GigFactory.build(
        property=PropertyFactory(), stipend_amount=Decimal("500"), deliverables=[REEL]
    )
    assert {"stipend_amount", "deliverables"} <= set(errors(gig, check_shape))


def test_malformed_deliverables_are_refused():
    gig = GigFactory.build(
        property=PropertyFactory(),
        compensation_model=CompensationModel.BARTER,
        deliverables=[{"type": "tattoo", "quantity": 1}],
    )
    assert "deliverables" in errors(gig, check_shape)


def test_drafts_may_be_incomplete_but_not_wrong():
    draft = GigFactory.build(
        property=PropertyFactory(),
        description="",
        start_date=None,
        end_date=None,
        apply_by=None,
        meals="",
    )
    check_shape(draft)
    draft.hours_per_day = 8
    assert "hours_per_day" in errors(draft, check_shape)


def test_only_own_live_property():
    gig = GigFactory.build(property=PropertyFactory())
    gig.vendor = PropertyFactory().vendor
    assert "property" in errors(gig, check_shape)


def test_dates_can_be_skipped_for_live_edits():
    gig = GigFactory.build(property=PropertyFactory(), start_date=in_days(-1), apply_by=in_days(-2))
    assert "start_date" in errors(gig)
    check_complete(gig, check_dates=False)
