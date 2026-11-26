"""Hour logs: the weekly cap and the day-off rule, warnings, and the host's review."""

from datetime import date, datetime, time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.applications.tests.helpers import live_gig
from apps.attendance import hours, services
from apps.attendance.hours import HoursError
from apps.attendance.models import HourLog
from apps.bookings.tests.helpers import booked
from apps.notifications.models import Notification
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def at(day: date, hour: int = 20):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def stay(hours_per_day=4, days_per_week=5):
    """A checked-in booking whose agreement says hours_per_day x days_per_week."""
    booking = booked(live_gig(hours_per_day=hours_per_day, days_per_week=days_per_week))
    terms = booking.agreement.current_version.terms
    assert (terms["hours_per_day"], terms["days_per_week"]) == (hours_per_day, days_per_week)
    attendance_pass = services.talent_pass(
        booking.pk, talent=booking.talent, now=at(booking.start_date, 9)
    )
    services.check_in(
        vendor=booking.vendor,
        method="qr",
        token=services.token_for(attendance_pass),
        scanned_at=at(booking.start_date, 10),
        now=at(booking.start_date, 10),
    )
    booking.refresh_from_db()
    return booking


def monday_in(booking) -> date:
    day = booking.start_date
    while day.weekday() != 0:
        day += timedelta(days=1)
    assert day + timedelta(days=6) <= booking.end_date
    return day


def log(booking, day, minutes, **kw):
    return hours.log(booking.pk, talent=booking.talent, day=day, minutes=minutes, now=at(day), **kw)


class TestRules:
    def test_the_weekly_cap_is_enforced(self):
        booking = stay(hours_per_day=4, days_per_week=5)  # 20 h a week
        monday = monday_in(booking)
        for i in range(4):
            log(booking, monday + timedelta(days=i), 4 * 60)
        with pytest.raises(HoursError, match="21 h this week; the agreed most is 20 h"):
            log(booking, monday + timedelta(days=4), 5 * 60)
        _, result = log(booking, monday + timedelta(days=4), 4 * 60)
        assert result.week_minutes == 20 * 60

    def test_the_day_off_rule_is_enforced(self):
        booking = stay(hours_per_day=2, days_per_week=5)
        monday = monday_in(booking)
        for i in range(5):
            log(booking, monday + timedelta(days=i), 60)
        with pytest.raises(HoursError, match=r"6 working days this week.*2 days off"):
            log(booking, monday + timedelta(days=5), 30)
        # The next week starts fresh.
        assert log(booking, monday + timedelta(days=7), 60)[1].week_days == 1

    def test_warnings_come_before_the_limits(self):
        booking = stay(hours_per_day=4, days_per_week=5)
        monday = monday_in(booking)
        for i in range(3):
            log(booking, monday + timedelta(days=i), 4 * 60)
        result = hours.preview(
            booking.pk,
            talent=booking.talent,
            day=monday + timedelta(days=3),
            minutes=6 * 60,
            now=at(monday + timedelta(days=3)),
        )
        assert result.allowed
        assert any("more than the 4 hours a day" in w for w in result.warnings)
        assert any("18 h of 20 h" in w for w in result.warnings)
        log(booking, monday + timedelta(days=3), 2 * 60)
        last = hours.preview(
            booking.pk,
            talent=booking.talent,
            day=monday + timedelta(days=4),
            minutes=60,
            now=at(monday + timedelta(days=4)),
        )
        assert any("rest of the week off" in w for w in last.warnings)
        assert not HourLog.objects.filter(day=monday + timedelta(days=4)).exists()  # a preview

    def test_relogging_a_day_replaces_it(self):
        booking = stay()
        day = booking.start_date
        log(booking, day, 60)
        entry, _ = log(booking, day, 90, note="Extra shoot")
        assert HourLog.objects.get().minutes == 90 and entry.note == "Extra shoot"

    @pytest.mark.parametrize(
        ("offset", "message"),
        [(-1, "isn't part of the stay"), (400, "isn't part of the stay")],
    )
    def test_days_outside_the_stay_are_refused(self, offset, message):
        booking = stay()
        with pytest.raises(HoursError, match=message):
            log(booking, booking.start_date + timedelta(days=offset), 60)

    def test_future_days_and_unstarted_stays_are_refused(self):
        booking = stay()
        with pytest.raises(HoursError, match="hasn't happened"):
            hours.log(
                booking.pk,
                talent=booking.talent,
                day=booking.start_date + timedelta(days=2),
                minutes=60,
                now=at(booking.start_date),
            )
        with pytest.raises(HoursError, match="once you've checked in"):
            unstarted = booked()
            log(unstarted, unstarted.start_date, 60)


class TestReview:
    def test_confirm_and_dispute(self):
        booking = stay()
        day = booking.start_date
        entry, _ = log(booking, day, 120)
        with pytest.raises(HoursError, match="what's wrong"):
            hours.review(entry.pk, vendor=booking.vendor, confirm=False)
        disputed = hours.review(entry.pk, vendor=booking.vendor, confirm=False, note="Left at noon")
        assert disputed.status == "disputed"
        note = Notification.objects.get(user=booking.talent, kind="attendance.hours_disputed")
        assert "Left at noon" in note.body
        # The talent corrects it; it goes back to the host.
        entry, _ = log(booking, day, 90)
        assert entry.status == "pending"
        assert hours.review(entry.pk, vendor=booking.vendor, confirm=True).status == "confirmed"
        with pytest.raises(HoursError, match="already answered"):
            hours.review(entry.pk, vendor=booking.vendor, confirm=True)
        with pytest.raises(HoursError, match="can't change now"):
            log(booking, day, 60)

    def test_only_the_bookings_host_reviews(self):
        booking = stay()
        entry, _ = log(booking, booking.start_date, 60)
        with pytest.raises(HourLog.DoesNotExist):
            hours.review(entry.pk, vendor=booked().vendor, confirm=True)


class TestApi:
    def test_logging_checking_and_reviewing(self, monkeypatch):
        booking = stay()
        evening = at(booking.start_date)

        class OnTheFirstDay:  # the API uses the real clock; the stay is weeks away
            now = staticmethod(lambda: evening)
            localdate = staticmethod(lambda value=None: timezone.localdate(value or evening))

        monkeypatch.setattr(hours, "timezone", OnTheFirstDay)
        talent, vendor = client_for(booking.talent), client_for(booking.vendor)
        day = booking.start_date.isoformat()
        check = talent.post(
            reverse("attendance:hours-check", args=[booking.pk]),
            {"day": day, "minutes": 60},
            format="json",
        )
        assert check.status_code == 200 and check.json()["allowed"] is True
        too_much = talent.post(
            reverse("attendance:hours", args=[booking.pk]),
            {"day": day, "minutes": 24 * 60},
            format="json",
        )
        assert too_much.status_code == 409 and "agreed most" in too_much.json()["message"]
        created = talent.post(
            reverse("attendance:hours", args=[booking.pk]),
            {"day": day, "minutes": 60},
            format="json",
        )
        assert created.status_code == 201
        pending = vendor.get(reverse("attendance:hours-pending")).json()
        assert pending["results"][0]["minutes"] == 60
        log_id = created.json()["log"]["id"]
        reviewed = vendor.post(
            reverse("attendance:hours-review", args=[log_id]), {"confirm": True}, format="json"
        )
        assert reviewed.json()["status"] == "confirmed"
        week = talent.get(reverse("attendance:hours", args=[booking.pk]), {"week": day}).json()
        assert week["minutes"] == 60 and week["weekly_cap_minutes"] == 20 * 60

    def test_permissions(self):
        booking = stay()
        url = reverse("attendance:hours", args=[booking.pk])
        assert (
            client_for(booking.vendor)
            .post(url, {"day": "2026-01-01", "minutes": 60}, format="json")
            .status_code
            == 403
        )
        assert client_for(booked().talent).get(url).status_code == 404
