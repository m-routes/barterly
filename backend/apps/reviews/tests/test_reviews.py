"""Reviews: who may write them and when, double-blind publishing, the 14-day window,
moderation, replies, reports, and that published reviews can't change."""

from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory
from apps.backoffice.roles import AdminRole, sync_roles
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.services import transition
from apps.bookings.tests.helpers import booked
from apps.common.models import AuditLog
from apps.notifications.models import Notification
from apps.reviews import services
from apps.reviews.models import Review, ReviewStatus
from apps.reviews.services import ReviewError
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
S = ReviewStatus
GOOD = "Lovely hosts, clear tasks and a calm room. Would come back."


def at(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def completed_stay():
    booking = booked()
    now = at(booking.start_date)
    for to, who, user in (
        (BookingStatus.CHECKED_IN, Actor.VENDOR, booking.vendor),
        (BookingStatus.DELIVERING, Actor.TALENT, booking.talent),
        (BookingStatus.COMPLETED, Actor.VENDOR, booking.vendor),
    ):
        transition(booking.pk, to, actor=who, user=user, now=now)
    booking.refresh_from_db()
    return booking


def write(booking, author, *, rating=5, text=GOOD, now=None, **scores):
    scores = {"communication": 5, "accuracy": 5, "safety": 5, "reliability": 5, **scores}
    return services.submit(
        booking.pk,
        author=author,
        rating=rating,
        text=text,
        now=now or booking.completed_at + timedelta(hours=1),
        **scores,
    )


class TestWriting:
    def test_only_completed_stays_once_each_within_the_window(self):
        booking = booked()
        with pytest.raises(ReviewError, match="once the stay is completed"):
            services.submit(
                booking.pk,
                author=booking.talent,
                rating=5,
                text=GOOD,
                communication=5,
                accuracy=5,
                safety=5,
                reliability=5,
            )
        booking = completed_stay()
        review = write(booking, booking.talent)
        assert (review.subject_id, review.subject_side) == (booking.vendor_id, "host")
        with pytest.raises(ReviewError, match="already reviewed"):
            write(booking, booking.talent)
        with pytest.raises(ReviewError, match="time to review"):
            write(booking, booking.vendor, now=booking.completed_at + timedelta(days=14))
        with pytest.raises(services.Booking.DoesNotExist):
            write(booking, TalentFactory())

    def test_reviews_need_some_words(self):
        booking = completed_stay()
        with pytest.raises(ReviewError, match="at least 20 characters"):
            write(booking, booking.talent, text="Great!")

    def test_categories_are_labelled_for_who_was_reviewed(self):
        assert services.CATEGORY_LABELS["host"]["accuracy"] == "Accuracy of the listing"
        assert services.CATEGORY_LABELS["host"]["reliability"] == "Payment as agreed"
        assert services.CATEGORY_LABELS["talent"]["accuracy"] == "Quality of the work"
        assert services.CATEGORY_LABELS["talent"]["reliability"] == "Punctuality"


class TestDoubleBlind:
    def test_hidden_until_both_are_in_then_published_together(self):
        booking = completed_stay()
        first = write(booking, booking.talent)
        assert first.status == S.SUBMITTED and first.published_at is None
        # The host hears they were reviewed, but can't read it yet.
        assert Notification.objects.filter(
            user=booking.vendor, kind="reviews.awaiting_yours"
        ).exists()
        view = client_for(booking.vendor).get(reverse("reviews:booking", args=[booking.pk]))
        body = view.json()
        assert body["theirs"] is None and body["they_have_reviewed"] is True
        assert body["can_review"] is True and body["reviewing"] == "talent"
        second = write(booking, booking.vendor, rating=4)
        first.refresh_from_db()
        second.refresh_from_db()
        assert first.status == second.status == S.PUBLISHED
        assert first.published_at == second.published_at
        booking.refresh_from_db()
        assert booking.status == BookingStatus.REVIEWED
        body = client_for(booking.vendor).get(reverse("reviews:booking", args=[booking.pk])).json()
        assert body["theirs"]["rating"] == 5 and body["mine"]["rating"] == 4
        assert {n.user_id for n in Notification.objects.filter(kind="reviews.published")} == {
            booking.talent_id,
            booking.vendor_id,
        }

    def test_the_window_closing_publishes_a_lone_review(self):
        booking = completed_stay()
        review = write(booking, booking.talent)
        assert services.close_windows(booking.completed_at + timedelta(days=13)) == {
            "published": 0,
            "reminded": 1,  # the host hasn't reviewed: two days left
        }
        assert (
            services.close_windows(booking.completed_at + timedelta(days=14, hours=1))["published"]
            == 1
        )
        review.refresh_from_db()
        assert review.status == S.PUBLISHED
        assert (
            Notification.objects.filter(user=booking.vendor, kind="reviews.window_closing").count()
            == 1
        )


class TestModeration:
    def test_flagged_words_and_contact_details_hold_a_review(self):
        booking = completed_stay()
        held = write(
            booking, booking.talent, text="Total scam, message me on 98765 43210 before you book."
        )
        assert held.status == S.HELD
        assert set(held.flags) == {"word:scam", "contact:phone"}
        # Its pair waits, so they still publish together.
        other = write(booking, booking.vendor)
        assert other.status == S.SUBMITTED
        admin = moderator()
        services.moderate(held.pk, admin=admin, decision="allow", note="Fair complaint")
        held.refresh_from_db()
        other.refresh_from_db()
        assert held.status == other.status == S.PUBLISHED
        assert AuditLog.objects.filter(action="reviews.moderated_allow").exists()

    def test_a_removed_review_never_shows_and_its_pair_publishes(self):
        booking = completed_stay()
        held = write(booking, booking.talent, text="Email me at someone@example.com for more")
        other = write(booking, booking.vendor)
        services.moderate(held.pk, admin=moderator(), decision="remove", note="Contact info")
        held.refresh_from_db()
        other.refresh_from_db()
        assert held.status == S.REMOVED and other.status == S.PUBLISHED

    @pytest.mark.parametrize(
        ("text", "flags"),
        [
            ("Visit www.example.com for my portfolio, lovely stay", ["contact:link"]),
            ("Call +91 98123-45678 if you need a photographer", ["contact:phone"]),
            ("Paid me on time and the room was spotless and calm", []),
            ("The scampi at the café was the best I've had", []),  # not "scam"
        ],
    )
    def test_what_gets_flagged(self, text, flags):
        from apps.reviews.moderation import flags_for

        assert flags_for(text) == flags

    def test_reports_queue_a_review_for_moderators(self):
        booking = completed_stay()
        review = write(booking, booking.talent)
        write(booking, booking.vendor)
        reader = TalentFactory()
        url = reverse("reviews:report", args=[review.pk])
        assert client_for(reader).post(url, {"reason": "false"}, format="json").status_code == 201
        assert client_for(reader).post(url, {"reason": "false"}, format="json").status_code == 409
        admin = moderator()
        queue = client_for(admin).get(reverse("reviews:queue")).json()
        assert [r["id"] for r in queue["results"]] == [str(review.pk)]
        assert queue["results"][0]["reports"][0]["reason"] == "false"
        assert client_for(AdminUserFactory()).get(reverse("reviews:queue")).status_code == 403
        decided = client_for(admin).post(
            reverse("reviews:moderate", args=[review.pk]),
            {"decision": "allow", "note": "Checked with the host"},
            format="json",
        )
        assert decided.status_code == 200
        assert client_for(admin).get(reverse("reviews:queue")).json()["count"] == 0


def moderator():
    sync_roles()
    user = AdminUserFactory()
    user.groups.add(Group.objects.get(name=AdminRole.TRUST))
    return user


class TestPublishedIsFinal:
    def published_pair(self):
        booking = completed_stay()
        mine = write(booking, booking.talent)
        write(booking, booking.vendor)
        mine.refresh_from_db()
        return booking, mine

    def test_the_database_refuses_edits_and_deletes(self):
        _, review = self.published_pair()
        for sql in (
            "UPDATE reviews_review SET text = 'changed' WHERE id = %s",
            "UPDATE reviews_review SET rating = 1 WHERE id = %s",
            "DELETE FROM reviews_review WHERE id = %s",
        ):
            with (
                pytest.raises(DatabaseError, match=r"can't be edited|never deleted"),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute(sql, [str(review.pk)])
        # Moderation can still remove it.
        Review.objects.filter(pk=review.pk).update(status=S.REMOVED)

    def test_one_reply_from_the_reviewed_person(self):
        booking, review = self.published_pair()
        with pytest.raises(Review.DoesNotExist):
            services.reply(review.pk, user=booking.talent, text="Thanks!")  # not about them
        services.reply(review.pk, user=booking.vendor, text="Thank you for staying with us!")
        with pytest.raises(ReviewError, match="already replied"):
            services.reply(review.pk, user=booking.vendor, text="Again")
        with (
            pytest.raises(DatabaseError, match="can't be edited"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute("UPDATE reviews_reply SET text = 'changed'")
        listed = (
            client_for(TalentFactory())
            .get(reverse("reviews:of-user", args=[booking.vendor_id]), {"side": "host"})
            .json()
        )
        assert listed["results"][0]["reply"]["text"] == "Thank you for staying with us!"

    def test_no_reply_before_publishing(self):
        booking = completed_stay()
        review = write(booking, booking.talent)
        with pytest.raises(ReviewError, match="once the review is published"):
            services.reply(review.pk, user=booking.vendor, text="Hi")


class TestApi:
    def test_submit_validates_the_stars(self):
        booking = completed_stay()
        url = reverse("reviews:booking", args=[booking.pk])
        body = {
            "rating": 6,
            "communication": 5,
            "accuracy": 5,
            "safety": 5,
            "reliability": 5,
            "text": GOOD,
        }
        assert client_for(booking.talent).post(url, body, format="json").status_code == 400
        body["rating"] = 5
        created = client_for(booking.talent).post(url, body, format="json")
        assert created.status_code == 201
        assert [c["label"] for c in created.json()["categories"]] == [
            "Communication",
            "Accuracy of the listing",
            "Safety",
            "Payment as agreed",
        ]
        assert client_for(TalentFactory()).get(url).status_code == 404

    def test_only_published_reviews_are_listed(self):
        booking = completed_stay()
        write(booking, booking.talent)
        url = reverse("reviews:of-user", args=[booking.vendor_id])
        assert client_for(TalentFactory()).get(url, {"side": "host"}).json()["count"] == 0
