"""Deliverables: created from the agreement, submitted with the label check, reviewed in
at most two rounds of changes, stats, reminders, the library, and escrow's window."""

from datetime import date, datetime, time, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.applications.tests.helpers import live_gig
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.services import transition
from apps.bookings.tests.helpers import booked
from apps.common.models import AuditLog
from apps.deliverables import services
from apps.deliverables.models import Deliverable, PostStats, Status
from apps.deliverables.services import DeliverableError
from apps.deliverables.stats.base import Stats
from apps.deliverables.stats.providers import FakeProvider
from apps.gigs.constants import CompensationModel
from apps.media.models import MediaStatus
from apps.notifications.models import Notification
from apps.verification.tests.factories import MediaFileFactory, client_for

pytestmark = pytest.mark.django_db
REEL = "https://www.instagram.com/reel/Cabc123/"
SPEC = [
    {"type": "instagram_reel", "quantity": 2, "notes": "Show the rooftop"},
    {"type": "photo_set", "quantity": 1, "notes": ""},
]


def at(day: date, hour: int = 10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def barter_stay(spec=SPEC, *, model=CompensationModel.BARTER, check_in=True, **gig):
    booking = booked(live_gig(compensation_model=model, deliverables=spec, **gig))
    if check_in:
        transition(
            booking.pk,
            BookingStatus.CHECKED_IN,
            actor=Actor.VENDOR,
            user=booking.vendor,
            now=at(booking.start_date),
        )
        booking.refresh_from_db()
    return booking


def items(booking):
    return list(Deliverable.objects.filter(booking=booking).order_by("spec_index", "unit"))


def hand_in(deliverable, *, url=REEL, confirmed=True, **kw):
    return services.submit(
        deliverable.pk,
        talent=deliverable.booking.talent,
        post_url=url,
        disclosure_confirmed=confirmed,
        **kw,
    )


class TestFromTheAgreement:
    def test_one_per_unit_at_check_in(self):
        booking = barter_stay()
        reel1, reel2, photos = items(booking)
        assert (reel1.title, reel2.title, photos.title) == (
            "Instagram reel 1 of 2",
            "Instagram reel 2 of 2",
            "Edited photo set",
        )
        assert (reel1.kind, reel1.platform, reel1.disclosure_required) == (
            "reel",
            "instagram",
            True,
        )
        assert (photos.kind, photos.platform, photos.disclosure_required) == (
            "photo_set",
            "other",
            False,
        )
        assert reel1.due_date == booking.end_date and reel1.notes == "Show the rooftop"
        services.create_for(booking)  # again: nothing new
        assert Deliverable.objects.filter(booking=booking).count() == 3

    def test_google_reviews_and_others(self):
        booking = barter_stay(
            [
                {"type": "google_review", "quantity": 1},
                {"type": "youtube_video", "quantity": 1},
                {"type": "mural", "quantity": 1},
            ]
        )
        review, video, mural = items(booking)
        assert (review.kind, review.platform, review.disclosure_required) == (
            "google_review",
            "google",
            True,
        )
        assert (video.kind, video.platform) == ("custom", "youtube")
        assert (mural.kind, mural.disclosure_required) == ("custom", False)

    def test_volunteer_stays_have_none(self):
        booking = booked()
        transition(
            booking.pk,
            BookingStatus.CHECKED_IN,
            actor=Actor.VENDOR,
            user=booking.vendor,
            now=at(booking.start_date),
        )
        assert not Deliverable.objects.filter(booking=booking).exists()


class TestSubmitting:
    def test_a_post_with_the_label(self):
        booking = barter_stay()
        reel = items(booking)[0]
        with pytest.raises(DeliverableError, match="link, or upload"):
            services.submit(reel.pk, talent=booking.talent, disclosure_confirmed=True)
        with pytest.raises(DeliverableError, match="collaboration label"):
            hand_in(reel, confirmed=False)
        submission = hand_in(reel)
        reel.refresh_from_db()
        assert reel.status == Status.SUBMITTED and submission.version == 1
        assert Notification.objects.filter(
            user=booking.vendor, kind="deliverables.submitted"
        ).exists()
        assert hand_in(reel).version == 2  # a fix before the host looks

    def test_files_must_be_the_talents_and_usable(self):
        booking = barter_stay()
        photos = items(booking)[2]
        mine = MediaFileFactory(owner=booking.talent)
        theirs = MediaFileFactory()
        broken = MediaFileFactory(owner=booking.talent, status=MediaStatus.QUARANTINED)
        for bad in (theirs, broken):
            with pytest.raises(DeliverableError, match="can't be used"):
                services.submit(photos.pk, talent=booking.talent, file_ids=[bad.pk])
        submission = services.submit(photos.pk, talent=booking.talent, file_ids=[mine.pk])
        assert list(submission.files.all()) == [mine]

    def test_only_after_check_in(self):
        booking = barter_stay(check_in=False)
        services.create_for(booking)
        with pytest.raises(DeliverableError, match="checked in"):
            hand_in(items(booking)[0])

    def test_the_label_is_checked_in_the_caption(self, django_capture_on_commit_callbacks):
        booking = barter_stay()
        reel, reel2, _ = items(booking)
        FakeProvider.answers[REEL] = Stats("instagram", 900, 80, 12, caption="Sunset! #ad #goa")
        with django_capture_on_commit_callbacks(execute=True):
            labelled = hand_in(reel)
        other = "https://www.instagram.com/reel/Cxyz/"
        FakeProvider.answers[other] = Stats("instagram", 10, 1, 0, caption="Sunset in Goa")
        with django_capture_on_commit_callbacks(execute=True):
            unlabelled = hand_in(reel2, url=other)
        labelled.refresh_from_db()
        unlabelled.refresh_from_db()
        assert labelled.disclosure_detected is True
        assert unlabelled.disclosure_detected is False
        assert PostStats.objects.get(deliverable=reel).views == 900

    def test_the_last_one_starts_the_hosts_window(self):
        booking = barter_stay()
        for d in items(booking):
            hand_in(d)
        note = Notification.objects.get(user=booking.vendor, kind="deliverables.all_submitted")
        assert "72 hours" in note.body


class TestReview:
    def test_approve(self):
        booking = barter_stay()
        reel = items(booking)[0]
        hand_in(reel)
        reviewed = services.review(reel.pk, vendor=booking.vendor, approve=True)
        assert reviewed.status == Status.APPROVED and reviewed.approved_at
        with pytest.raises(DeliverableError, match="approved already"):
            hand_in(reel)

    def test_at_most_two_rounds_of_changes(self):
        booking = barter_stay()
        reel = items(booking)[0]
        for round_ in (1, 2):
            hand_in(reel)
            with pytest.raises(DeliverableError, match="what needs to change"):
                services.review(reel.pk, vendor=booking.vendor, approve=False)
            reviewed = services.review(
                reel.pk, vendor=booking.vendor, approve=False, note=f"Round {round_}: brighter"
            )
            assert reviewed.change_rounds == round_
        note = Notification.objects.filter(
            user=booking.talent, kind="deliverables.changes_requested"
        ).first()
        assert "brighter" in note.body
        hand_in(reel)
        with pytest.raises(
            DeliverableError, match=r"both rounds of changes\. Approve it, or open a dispute"
        ):
            services.review(reel.pk, vendor=booking.vendor, approve=False, note="Again")
        assert services.review(reel.pk, vendor=booking.vendor, approve=True).status == "approved"

    def test_the_database_caps_the_rounds(self):
        booking = barter_stay()
        with pytest.raises(IntegrityError), transaction.atomic():
            Deliverable.objects.filter(pk=items(booking)[0].pk).update(change_rounds=3)

    def test_only_the_bookings_host_reviews(self):
        booking = barter_stay()
        reel = items(booking)[0]
        hand_in(reel)
        with pytest.raises(Deliverable.DoesNotExist):
            services.review(reel.pk, vendor=barter_stay().vendor, approve=True)

    def test_due_dates_move_within_limits(self):
        booking = barter_stay()
        reel = items(booking)[0]
        with pytest.raises(DeliverableError, match="within 30 days"):
            services.set_due_date(
                reel.pk, vendor=booking.vendor, due_date=booking.end_date + timedelta(days=31)
            )
        moved = services.set_due_date(
            reel.pk, vendor=booking.vendor, due_date=booking.start_date + timedelta(days=3)
        )
        assert moved.due_date == booking.start_date + timedelta(days=3)
        assert AuditLog.objects.filter(action="deliverables.due_date_changed").exists()
        assert Notification.objects.filter(kind="deliverables.due_date_changed").exists()


class TestStats:
    def test_self_reported_numbers_need_a_screenshot(self):
        booking = barter_stay()
        reel = items(booking)[0]
        with pytest.raises(DeliverableError, match="Submit the post first"):
            services.report_stats(reel.pk, talent=booking.talent, views=5, screenshot_id=None)
        hand_in(reel)
        with pytest.raises(DeliverableError, match="screenshot"):
            services.report_stats(
                reel.pk, talent=booking.talent, views=5, screenshot_id=MediaFileFactory().pk
            )
        shot = MediaFileFactory(owner=booking.talent)
        stats = services.report_stats(
            reel.pk, talent=booking.talent, views=1200, likes=90, screenshot_id=shot.pk
        )
        assert stats.self_reported and stats.source == "manual"
        with pytest.raises(IntegrityError), transaction.atomic():
            PostStats.objects.create(deliverable=reel, source="manual", views=1)

    def test_the_job_refreshes_platform_numbers_once_a_day(self):
        booking = barter_stay()
        reel = items(booking)[0]
        hand_in(reel)
        FakeProvider.answers[REEL] = Stats("instagram", 100, 10, 1)
        now = timezone.now()
        assert services.refresh_all(now) == {"updated": 1}
        assert services.refresh_all(now + timedelta(hours=2)) == {"updated": 0}
        FakeProvider.answers[REEL] = Stats("instagram", 400, 30, 4)
        assert services.refresh_all(now + timedelta(hours=21)) == {"updated": 1}
        assert PostStats.objects.filter(deliverable=reel).first().views == 400


class TestReminders:
    def test_two_days_before_on_the_day_and_after(self):
        booking = barter_stay()
        reel, reel2, photos = items(booking)
        today = booking.start_date + timedelta(days=1)
        Deliverable.objects.filter(pk=reel.pk).update(due_date=today + timedelta(days=2))
        Deliverable.objects.filter(pk=reel2.pk).update(due_date=today)
        Deliverable.objects.filter(pk=photos.pk).update(due_date=today - timedelta(days=1))
        now = at(today, 9)
        assert services.send_reminders(now) == {"reminders": 3}
        services.send_reminders(now + timedelta(hours=1))  # a rerun adds nothing
        kinds = sorted(
            Notification.objects.filter(
                user=booking.talent, kind__startswith="deliverables.due"
            ).values_list("kind", flat=True)
        )
        assert kinds == [
            "deliverables.due_in_two_days",
            "deliverables.due_overdue",
            "deliverables.due_today",
        ]

    def test_handed_in_ones_get_none(self):
        booking = barter_stay()
        reel = items(booking)[0]
        hand_in(reel)
        Deliverable.objects.filter(pk=reel.pk).update(due_date=booking.start_date)
        services.send_reminders(at(booking.start_date, 9))
        assert not Notification.objects.filter(
            kind="deliverables.due_today", payload__deliverable_id=str(reel.pk)
        ).exists()


class TestLibrary:
    def test_approved_content_with_usage_rights_and_downloads(self):
        booking = barter_stay()
        photos = items(booking)[2]
        files = [
            MediaFileFactory(owner=booking.talent),
            MediaFileFactory(
                owner=booking.talent, content_type="video/mp4", object_key="test/clip.mp4"
            ),
        ]
        services.submit(photos.pk, talent=booking.talent, file_ids=[f.pk for f in files])
        approved_at = timezone.make_aware(datetime(2027, 1, 31, 12))
        services.review(photos.pk, vendor=booking.vendor, approve=True, now=approved_at)
        client = client_for(booking.vendor)
        body = client.get(reverse("deliverables:library")).json()
        item = body["results"][0]
        assert item["usage_rights"] == {
            "scope": "organic",
            "duration_months": 12,
            "credit_required": True,
        }
        assert item["usable_until"] == "2028-01-31"
        assert [d["content_type"] for d in item["downloads"]] == ["image/jpeg", "video/mp4"]
        assert all("download=1" in d["url"] for d in item["downloads"])
        assert client_for(booking.talent).get(reverse("deliverables:library")).status_code == 403

    def test_usage_rights_show_only_once_approved(self):
        booking = barter_stay()
        reel = items(booking)[0]
        hand_in(reel)
        rows = (
            client_for(booking.vendor)
            .get(reverse("deliverables:for-booking", args=[booking.pk]))
            .json()
        )
        assert rows[0]["usage_rights"] is None and rows[0]["status"] == "submitted"
        assert rows[0]["latest_submission"]["disclosure_confirmed"] is True
        listed = client_for(booking.vendor).get(reverse("deliverables:to-review")).json()
        assert [r["id"] for r in listed["results"]] == [str(reel.pk)]

    def test_usable_until_handles_short_months(self):
        booking = barter_stay()
        assert services.usable_until(
            booking, timezone.make_aware(datetime(2027, 3, 31, 12))
        ) == date(2028, 3, 31)


class TestApi:
    def test_submit_review_and_stats_endpoints(self):
        booking = barter_stay()
        reel = items(booking)[0]
        talent, vendor = client_for(booking.talent), client_for(booking.vendor)
        refused = talent.post(
            reverse("deliverables:submit", args=[reel.pk]), {"post_url": REEL}, format="json"
        )
        assert refused.status_code == 400
        done = talent.post(
            reverse("deliverables:submit", args=[reel.pk]),
            {"post_url": REEL, "disclosure_confirmed": True},
            format="json",
        )
        assert done.status_code == 201 and done.json()["status"] == "submitted"
        shot = MediaFileFactory(owner=booking.talent)
        stats = talent.post(
            reverse("deliverables:stats", args=[reel.pk]),
            {"views": 50, "screenshot_id": str(shot.pk)},
            format="json",
        )
        assert stats.json()["self_reported"] is True and stats.json()["screenshot_url"]
        assert (
            vendor.post(
                reverse("deliverables:submit", args=[reel.pk]), {}, format="json"
            ).status_code
            == 403
        )
        reviewed = vendor.post(
            reverse("deliverables:review", args=[reel.pk]), {"approve": True}, format="json"
        )
        assert reviewed.json()["usage_rights"]["scope"] == "organic"
        moved = vendor.patch(
            reverse("deliverables:item", args=[items(booking)[1].pk]),
            {"due_date": str(booking.start_date)},
            format="json",
        )
        assert moved.status_code == 200

    def test_strangers_see_nothing(self):
        booking = barter_stay()
        other = barter_stay()
        url = reverse("deliverables:for-booking", args=[booking.pk])
        assert client_for(other.talent).get(url).status_code == 404
