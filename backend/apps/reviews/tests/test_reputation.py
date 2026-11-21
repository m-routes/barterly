"""Reputation: ratings, completion rate, response time, badges from configured rules,
and the review signals in the reliability score."""

from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import TalentFactory
from apps.applications.tests.helpers import dates, live_gig
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.services import transition
from apps.bookings.tests.helpers import booked
from apps.chat.models import Conversation, Message
from apps.gigs.constants import CompensationModel
from apps.reliability.models import ReliabilityScore
from apps.reviews import badges, reputation
from apps.reviews.models import Reputation, Side
from apps.reviews.tests.test_reviews import at, completed_stay, write
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db

RULES = [
    {
        "key": "top_volunteer",
        "label": "Top Volunteer",
        "side": "talent",
        "all": [
            {"metric": "completed_volunteer_gigs", "min": 3},
            {"metric": "rating_average", "min": 4.5},
            {"metric": "no_shows", "max": 0},
        ],
    },
    {
        "key": "trusted_member",
        "label": "Trusted member",
        "side": "any",
        "all": [{"metric": "clean_gigs", "min": 5}, {"metric": "no_shows", "max": 0}],
    },
]


class TestBadgeRules:
    def test_the_configured_rules_are_valid(self):
        badges.check_rules()  # what settings ship with

    @pytest.mark.parametrize(
        ("rule", "message"),
        [
            (
                {"label": "X", "side": "talent", "all": [{"metric": "completed", "min": 1}]},
                "key and a label",
            ),
            (
                {
                    "key": "x",
                    "label": "X",
                    "side": "everyone",
                    "all": [{"metric": "completed", "min": 1}],
                },
                "side must be",
            ),
            ({"key": "x", "label": "X", "side": "any", "all": []}, "at least one condition"),
            (
                {
                    "key": "x",
                    "label": "X",
                    "side": "any",
                    "all": [{"metric": "followers", "min": 1}],
                },
                "unknown metric",
            ),
            (
                {
                    "key": "x",
                    "label": "X",
                    "side": "any",
                    "all": [{"metric": "completed", "above": 1}],
                },
                "min and/or max",
            ),
        ],
    )
    def test_bad_rules_fail_at_startup(self, rule, message):
        with pytest.raises(ImproperlyConfigured, match=message):
            badges.check_rules([rule])

    def test_duplicate_keys_fail(self):
        with pytest.raises(ImproperlyConfigured, match="used twice"):
            badges.check_rules([RULES[0], RULES[0]])

    def test_every_condition_must_hold(self):
        strong = {
            "completed_volunteer_gigs": 3,
            "rating_average": 4.6,
            "no_shows": 0,
            "clean_gigs": 5,
        }
        assert [b["key"] for b in badges.award("talent", strong, RULES)] == [
            "top_volunteer",
            "trusted_member",
        ]
        assert [b["key"] for b in badges.award("host", strong, RULES)] == ["trusted_member"]
        assert badges.award("talent", {**strong, "no_shows": 1}, RULES) == []
        no_reviews = {**strong, "rating_average": None}  # unknown fails a condition
        assert [b["key"] for b in badges.award("talent", no_reviews, RULES)] == ["trusted_member"]

    def test_the_shipped_badges(self, settings):
        def keys(side, **metrics):
            base = {m: 0 for m in badges.METRICS} | {"rating_average": None}
            return [b["key"] for b in badges.award(side, base | metrics)]

        assert keys(
            "talent",
            id_verified=1,
            instagram_linked=1,
            completed_content_gigs=1,
            rating_average=4.2,
        ) == ["verified_creator"]
        assert (
            keys(
                "talent",
                id_verified=0,
                instagram_linked=1,
                completed_content_gigs=1,
                rating_average=4.9,
            )
            == []
        )
        assert keys("talent", completed_volunteer_gigs=3, rating_average=4.5) == ["top_volunteer"]
        n = settings.TRUSTED_MEMBER_CLEAN_GIGS
        assert keys("host", clean_gigs=n) == ["trusted_member"]
        assert keys("host", clean_gigs=n, late_cancellations=1) == []


class TestMetrics:
    def test_ratings_completion_and_clean_gigs(self):
        booking = completed_stay()
        write(booking, booking.talent, rating=5)
        write(booking, booking.vendor, rating=3)  # a 3-star review: not a clean gig
        host = reputation.metrics_for(booking.vendor_id, Side.HOST)
        talent = reputation.metrics_for(booking.talent_id, Side.TALENT)
        assert (host["review_count"], host["rating_average"]) == (1, 5.0)
        assert (host["completed"], host["completion_rate"], host["clean_gigs"]) == (1, 100, 1)
        assert (talent["rating_average"], talent["clean_gigs"]) == (3.0, 0)

    def test_no_shows_lower_the_completion_rate(self):
        done = completed_stay()
        missed = booked(talent=done.talent, **dates(52, 58))  # after the first stay
        transition(
            missed.pk,
            BookingStatus.NO_SHOW,
            actor=Actor.VENDOR,
            user=missed.vendor,
            reason="Never came",
            now=at(missed.start_date + timedelta(days=1)),
        )
        metrics = reputation.metrics_for(done.talent_id, Side.TALENT)
        assert (metrics["no_shows"], metrics["completion_rate"]) == (1, 50)

    def test_volunteer_and_content_gigs_are_told_apart(self):
        content = booked(
            live_gig(
                compensation_model=CompensationModel.BARTER,
                deliverables=[{"type": "photo_set", "quantity": 1}],
            )
        )
        for to, who, user in (
            (BookingStatus.CHECKED_IN, Actor.VENDOR, content.vendor),
            (BookingStatus.DELIVERING, Actor.TALENT, content.talent),
            (BookingStatus.COMPLETED, Actor.VENDOR, content.vendor),
        ):
            transition(content.pk, to, actor=who, user=user, now=at(content.start_date))
        metrics = reputation.metrics_for(content.talent_id, Side.TALENT)
        assert (metrics["completed_content_gigs"], metrics["completed_volunteer_gigs"]) == (1, 0)

    def test_response_time_is_the_median_reply(self):
        booking = completed_stay()
        talk = Conversation.objects.create(
            application=booking.application,
            talent=booking.talent,
            vendor=booking.vendor,
            opened_by="vendor",
        )
        start = timezone.now() - timedelta(days=2)
        # Host writes twice (the run counts from the first), talent replies 30 min later;
        # host writes, talent replies 10 min later; host writes, talent replies 2 h later.
        timeline = [("v", 0), ("v", 5), ("t", 30), ("v", 60), ("t", 70), ("v", 100), ("t", 220)]
        for seq, (who, minutes) in enumerate(timeline, start=1):
            message = Message.objects.create(
                conversation=talk,
                seq=seq,
                body="hi",
                sender=booking.vendor if who == "v" else booking.talent,
            )
            Message.objects.filter(pk=message.pk).update(
                created_at=start + timedelta(minutes=minutes)
            )
        assert reputation.response_minutes(booking.talent_id) == 30  # median of 30, 10, 120
        assert reputation.response_minutes(booking.vendor_id) == 30  # median of 30, 30
        assert reputation.response_minutes(TalentFactory().pk) is None


class TestRecompute:
    def test_publishing_updates_reputation_and_reliability(self):
        booking = completed_stay()
        write(booking, booking.talent, rating=5)
        assert not Reputation.objects.filter(user=booking.vendor, side="host", review_count=1)
        write(booking, booking.vendor, rating=2)
        host = Reputation.objects.get(user=booking.vendor, side="host")
        assert (host.review_count, str(host.rating_average)) == (1, "5.00")
        # Reliability v2: a good review for the host, a poor one for the talent.
        host_score = ReliabilityScore.objects.get(user=booking.vendor, side="vendor")
        talent_score = ReliabilityScore.objects.get(user=booking.talent, side="talent")
        assert (host_score.inputs["good_reviews"], talent_score.inputs["poor_reviews"]) == (1, 1)
        assert host_score.version == "v2"
        assert talent_score.breakdown["poor_reviews"] == -8

    def test_the_nightly_job_recomputes_everyone_recent(self):
        completed_stay()
        assert reputation.recompute_all(timezone.now()) == {"recomputed": 2}
        assert Reputation.objects.count() == 2

    def test_the_reputation_endpoint(self):
        booking = completed_stay()
        write(booking, booking.talent, rating=4)
        write(booking, booking.vendor, rating=5)
        body = (
            client_for(TalentFactory())
            .get(reverse("reviews:reputation", args=[booking.talent_id]))
            .json()
        )
        assert body["talent"]["rating_average"] == "5.00"
        assert body["talent"]["completion_rate"] == 100
        assert body["host"] == {
            "rating_average": None,
            "review_count": 0,
            "completion_rate": None,
            "response_minutes": None,
            "badges": [],
        }
