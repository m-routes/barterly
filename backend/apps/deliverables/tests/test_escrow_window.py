"""Hybrid gigs: handing in the last deliverable starts escrow's 72-hour window; asking
for changes stops it; approving everything releases the stipend at once."""

from datetime import timedelta

import pytest

from apps.applications.tests.helpers import live_gig
from apps.bookings.tests.helpers import booked
from apps.deliverables import services
from apps.deliverables.models import Deliverable
from apps.gigs.constants import CompensationModel
from apps.money import deliverables as single_submission
from apps.money import escrow
from apps.money.models import EscrowStatus
from apps.money.tests.helpers import check_in, day_one, funded, payout_account

pytestmark = pytest.mark.django_db
SPEC = [{"type": "instagram_reel", "quantity": 1}, {"type": "photo_set", "quantity": 1}]


def hybrid_stay():
    booking = booked(
        live_gig(
            compensation_model=CompensationModel.HYBRID,
            stipend_amount=5000,
            stipend_period="total",
            stay_type="none",
            deliverables=SPEC,
        )
    )
    booking, record = funded(booking)
    payout_account(booking.talent)
    check_in(booking)
    return booking, record, list(Deliverable.objects.filter(booking=booking).order_by("spec_index"))


def hand_in(d, now):
    return services.submit(
        d.pk,
        talent=d.booking.talent,
        post_url="https://youtu.be/abc123x",
        disclosure_confirmed=True,
        now=now,
    )


def test_the_window_starts_at_the_last_submission():
    booking, record, (reel, photos) = hybrid_stay()
    first = day_one(booking)
    hand_in(reel, first)
    # One handed in, one not: no window yet, however long it's been.
    assert escrow.auto_release(first + timedelta(days=10)) == {"released": 0}
    last = first + timedelta(days=2)
    hand_in(photos, last)
    assert escrow.auto_release(last + timedelta(hours=71)) == {"released": 0}
    assert escrow.auto_release(last + timedelta(hours=72, minutes=1)) == {"released": 1}
    record.refresh_from_db()
    assert (record.status, record.released_by) == (EscrowStatus.RELEASED, "system")


def test_asking_for_changes_stops_the_clock():
    booking, _, (reel, photos) = hybrid_stay()
    now = day_one(booking)
    hand_in(reel, now)
    hand_in(photos, now)
    services.review(photos.pk, vendor=booking.vendor, approve=False, note="Re-edit")
    assert escrow.auto_release(now + timedelta(days=5)) == {"released": 0}
    later = now + timedelta(days=5)
    hand_in(photos, later)
    assert escrow.auto_release(later + timedelta(hours=73)) == {"released": 1}


def test_approving_everything_releases_at_once():
    booking, record, (reel, photos) = hybrid_stay()
    now = day_one(booking)
    hand_in(reel, now)
    hand_in(photos, now)
    services.review(reel.pk, vendor=booking.vendor, approve=True)
    record.refresh_from_db()
    assert record.status == EscrowStatus.HELD  # one left
    services.review(photos.pk, vendor=booking.vendor, approve=True)
    record.refresh_from_db()
    assert (record.status, record.released_by) == (EscrowStatus.RELEASED, "vendor")


def test_an_approval_the_kill_switch_held_back_is_retried(settings):
    booking, record, (reel, photos) = hybrid_stay()
    now = day_one(booking)
    for d in (reel, photos):
        hand_in(d, now)
    settings.ESCROW_PAUSED = True
    for d in (reel, photos):
        services.review(d.pk, vendor=booking.vendor, approve=True)
    record.refresh_from_db()
    assert record.status == EscrowStatus.HELD
    settings.ESCROW_PAUSED = False
    assert escrow.auto_release(now + timedelta(hours=1)) == {"released": 1}
    record.refresh_from_db()
    assert record.released_by == "vendor"


def test_the_single_submission_flow_is_closed_to_tracked_bookings():
    booking, _, _ = hybrid_stay()
    with pytest.raises(single_submission.DeliverableError, match="its own card"):
        single_submission.submit(booking.pk, talent=booking.talent, note="All done")
