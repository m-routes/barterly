"""Counting events into the stored score, and showing it."""

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.bookings import cancellation
from apps.bookings.lifecycle import Actor
from apps.bookings.lifecycle import BookingStatus as B
from apps.bookings.services import transition
from apps.bookings.tests.helpers import accepted, booked, offered
from apps.common.models import AuditLog
from apps.offers import services as offers
from apps.offers.models import Offer
from apps.reliability.models import ReliabilityScore
from apps.reliability.services import inputs_for, recompute
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def stored(user, side) -> ReliabilityScore:
    return ReliabilityScore.objects.get(user=user, side=side)


def at(day):
    return timezone.make_aware(datetime.combine(day, time(10)))


def complete(booking):
    day = at(booking.start_date)
    transition(booking.pk, B.CHECKED_IN, actor=Actor.VENDOR, user=booking.vendor, now=day)
    transition(booking.pk, B.DELIVERING, actor=Actor.TALENT, user=booking.talent, now=day)
    transition(booking.pk, B.COMPLETED, actor=Actor.VENDOR, user=booking.vendor, now=day)


def test_answering_an_offer_counts_as_an_on_time_reply():
    booking = accepted()  # the talent accepted the host's offer
    talent = stored(booking.talent, "talent")
    assert talent.inputs["on_time_replies"] == 1
    assert (talent.score, talent.level) == (51, "new")


def test_a_lapsed_offer_earns_nothing():
    application = offered()
    assert inputs_for(application.talent_id, "talent").on_time_replies == 0


def test_the_host_answering_a_counter_counts_for_the_host():
    application = offered()
    offer = Offer.objects.get(application=application)
    countered = offers.counter(offer.pk, talent=application.talent, changes={"hours_per_day": 3})
    offers.decline(countered.pk, user=application.gig.vendor, reason="We need four")
    assert stored(application.gig.vendor, "vendor").inputs["on_time_replies"] == 1
    assert stored(application.talent, "talent").inputs["on_time_replies"] == 1


def test_completed_bookings_raise_both_sides():
    booking = booked()
    complete(booking)
    talent, host = stored(booking.talent, "talent"), stored(booking.vendor, "vendor")
    assert talent.inputs["completed"] == 1 and talent.score == 57  # 50 + 6 + 1 reply
    assert host.inputs["completed"] == 1 and host.score == 56
    assert talent.level == "fair"
    assert AuditLog.objects.filter(action="reliability.changed", object_id=str(talent.pk))


def test_a_late_cancellation_lowers_only_the_one_who_cancelled():
    booking = booked()
    cancellation.cancel(
        booking.pk,
        user=booking.talent,
        by="talent",
        reason="plans_changed",
        now=at(booking.start_date - timedelta(days=3)),
    )
    talent, host = stored(booking.talent, "talent"), stored(booking.vendor, "vendor")
    assert talent.inputs["late_cancellations"] == 1
    assert talent.score == 41  # 50 + 1 reply - 10
    assert host.inputs["late_cancellations"] == 0 and host.score == 50


def test_a_last_minute_cancellation_by_the_host_counts_double():
    booking = booked()
    cancellation.cancel(
        booking.pk,
        user=booking.vendor,
        by="vendor",
        reason="property_unavailable",
        now=at(booking.start_date - timedelta(days=1)),
    )
    host = stored(booking.vendor, "vendor")
    assert host.inputs["last_minute_cancellations"] == 1 and host.score == 30


def test_a_free_cancellation_costs_nothing():
    booking = booked()
    cancellation.cancel(booking.pk, user=booking.talent, by="talent", reason="illness")
    assert stored(booking.talent, "talent").score == 51


def test_a_no_show_lowers_the_talent_and_an_upheld_dispute_restores_it():
    booking = booked()
    transition(
        booking.pk,
        B.NO_SHOW,
        actor=Actor.VENDOR,
        user=booking.vendor,
        reason="Never arrived",
        now=at(booking.start_date + timedelta(days=1)),
    )
    assert stored(booking.talent, "talent").score == 26  # 50 + 1 - 25
    transition(booking.pk, B.DISPUTED, actor=Actor.TALENT, user=booking.talent, reason="I was")
    assert stored(booking.talent, "talent").inputs["no_shows"] == 0


def test_recompute_is_idempotent_and_quiet_when_nothing_changed():
    booking = booked()
    recompute(booking.talent_id, "talent")
    before = AuditLog.objects.filter(action="reliability.changed").count()
    recompute(booking.talent_id, "talent")
    assert AuditLog.objects.filter(action="reliability.changed").count() == before


def test_my_reliability_shows_both_sides_with_the_breakdown():
    booking = booked()
    body = client_for(booking.talent).get("/api/v1/reliability/me/").json()
    talent = next(row for row in body if row["side"] == "talent")
    assert talent["score"] == 51 and talent["breakdown"]["on_time_replies"] == 1
    host = next(row for row in body if row["side"] == "vendor")
    assert (host["score"], host["level"]) == (50, "new")
    assert client_for(None).get("/api/v1/reliability/me/").status_code == 401


def test_hosts_see_applicants_reliability_and_talent_see_the_hosts():
    application = offered()
    vendor, talent = client_for(application.gig.vendor), client_for(application.talent)
    listed = vendor.get(f"/api/v1/gigs/{application.gig_id}/applications/").json()
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert rows[0]["applicant"]["reliability"] == {"score": 50, "level": "new", "version": "v1"}
    thread = talent.get(f"/api/v1/applications/{application.pk}/offers/").json()
    assert thread["host_reliability"]["score"] == 50
