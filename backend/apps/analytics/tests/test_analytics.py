import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.analytics import kpis, services
from apps.analytics.events import EVENTS, clean
from apps.analytics.models import AnalyticsEvent, KpiSnapshot
from apps.applications.models import Application
from apps.applications.tests.helpers import live_gig
from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking, BookingEvent
from apps.privacy.models import Purpose
from apps.privacy.services import consents

pytestmark = pytest.mark.django_db

URL = reverse("analytics:events")
REPO = Path(__file__).resolve().parents[4]


def agree(user, granted=True):
    consents.record(user, Purpose.ANALYTICS, granted=granted, source="mobile")


def send(user, *events, platform="android"):
    api = APIClient()
    api.force_authenticate(user)
    return api.post(
        URL, {"platform": platform, "app_version": "1.4.0", "events": list(events)}, format="json"
    )


class TestConsent:
    def test_without_consent_nothing_is_kept(self):
        talent = TalentFactory()
        response = send(talent, {"name": "screen_view", "props": {"screen": "discover"}})
        assert response.status_code == 202
        assert response.json() == {"accepted": 0, "dropped": 1, "consent": False}
        assert not AnalyticsEvent.objects.exists()

    def test_with_consent_events_are_kept_under_a_pseudonym(self):
        talent = TalentFactory()
        agree(talent)
        response = send(talent, {"name": "screen_view", "props": {"screen": "discover"}})
        assert response.json()["accepted"] == 1
        event = AnalyticsEvent.objects.get()
        assert event.actor == services.actor_key(talent)
        assert str(talent.pk) not in event.actor
        assert event.props == {"screen": "discover"}
        assert event.role == "talent" and event.platform == "android"

    def test_withdrawing_consent_deletes_what_was_kept(self):
        talent = TalentFactory()
        agree(talent)
        send(talent, {"name": "apply_started", "props": {"gig_id": str(uuid.uuid4())}})
        other = TalentFactory()
        agree(other)
        send(other, {"name": "search", "props": {"filters": 2, "results": 14}})
        agree(talent, granted=False)
        assert list(AnalyticsEvent.objects.values_list("name", flat=True)) == ["search"]

    def test_erasure_deletes_them_too(self):
        from apps.privacy.services.erasure import _anonymisers

        talent = TalentFactory()
        agree(talent)
        send(talent, {"name": "search", "props": {"filters": 1, "results": 0}})
        step = dict(_anonymisers)["analytics_events"]
        assert step(talent, timezone.now()) == 1
        assert not AnalyticsEvent.objects.exists()

    def test_old_events_are_purged(self, settings):
        from apps.privacy.services.retention import purge

        talent = TalentFactory()
        agree(talent)
        send(talent, {"name": "search", "props": {"filters": 1, "results": 0}})
        AnalyticsEvent.objects.update(occurred_at=timezone.now() - timedelta(days=400))
        assert purge(timezone.now())["analytics_events"] == 1

    def test_anonymous_callers_are_refused(self):
        assert APIClient().post(URL, {}, format="json").status_code == 401


class TestAllowlist:
    def test_unknown_events_and_properties_are_dropped(self):
        talent = TalentFactory()
        agree(talent)
        response = send(
            talent,
            {"name": "screen_view", "props": {"screen": "trips/agreement", "phone": "+9198"}},
            {"name": "typed_a_message", "props": {"text": "hello"}},
            {"name": "search", "props": {"filters": "lots", "results": 3}},
        )
        assert response.json() == {"accepted": 2, "dropped": 1, "consent": True}
        props = sorted(AnalyticsEvent.objects.values_list("props", flat=True), key=str)
        assert props == [{"results": 3}, {"screen": "trips/agreement"}]

    def test_free_text_never_gets_in(self):
        assert clean("screen_view", {"screen": "Rohan's profile"}) == {}
        assert clean("feedback_sent", {"kind": "my phone is 98..."}) == {}
        assert clean("gig_viewed", {"gig_id": "not-a-uuid", "source": "search"}) == {
            "source": "search"
        }

    def test_stale_or_future_times_are_dropped(self):
        talent = TalentFactory()
        agree(talent)
        old = (timezone.now() - timedelta(days=10)).isoformat()
        future = (timezone.now() + timedelta(hours=2)).isoformat()
        response = send(
            talent,
            {"name": "search", "occurred_at": old, "props": {}},
            {"name": "search", "occurred_at": future, "props": {}},
        )
        assert response.json()["accepted"] == 0

    @pytest.mark.parametrize(
        ("path", "pattern"),
        [
            ("web/src/lib/analytics/events.ts", r"EVENT_NAMES = \[(.*?)\]"),
            ("mobile/lib/src/analytics/events.dart", r"eventNames = <String>\[(.*?)\]"),
        ],
    )
    def test_the_apps_list_the_same_events(self, path, pattern):
        import re

        listing = re.search(pattern, (REPO / path).read_text(), re.S).group(1)
        assert set(re.findall(r"""['"]([a-z_]+)['"]""", listing)) == set(EVENTS)


def _published(days_ago: float, **gig):
    gig = live_gig(**gig)
    gig.published_at = timezone.now() - timedelta(days=days_ago)
    gig.save(update_fields=["published_at"])
    return gig


class TestKpis:
    def test_applications_fill_rate_and_time_to_first_applicant(self):
        from apps.bookings.tests.helpers import accepted

        filled = _published(20)
        booking = accepted(filled)
        Application.objects.filter(pk=booking.application_id).update(
            applied_at=filled.published_at + timedelta(hours=6)
        )
        Booking.objects.filter(pk=booking.pk).update(
            created_at=filled.published_at + timedelta(days=3)
        )
        _published(18)  # mature, no applicants
        _published(2)  # too new to count for the 14-day metrics
        result = {k.key: k for k in kpis.compute(timezone.localdate(), 28)}

        assert result["applications_per_gig"].sample == 2
        assert result["applications_per_gig"].value == 0.5
        assert result["applications_per_gig"].status == "bad"  # target 8
        assert result["fill_rate_14d"].value == 0.5
        assert result["time_to_first_applicant"].value == 6.0
        assert "2 gigs with no applicant" in result["time_to_first_applicant"].note

    def test_no_show_completion_and_disputes(self):
        from apps.bookings.tests.helpers import booked

        today = timezone.localdate()
        bookings = [booked() for _ in range(3)]
        for b, status in zip(
            bookings,
            [BookingStatus.COMPLETED, BookingStatus.NO_SHOW, BookingStatus.REVIEWED],
            strict=True,
        ):
            Booking.objects.filter(pk=b.pk).update(
                status=status,
                start_date=today - timedelta(days=10),
                end_date=today - timedelta(days=3),
            )
        BookingEvent.objects.create(
            booking=bookings[0],
            from_state="completed",
            to_state="disputed",
            actor="talent",
            reason="x",
        )
        result = {k.key: k for k in kpis.compute(today, 28)}
        assert result["no_show_rate"].value == pytest.approx(1 / 3, abs=1e-3)
        assert result["no_show_rate"].status == "bad"  # target under 5%
        assert result["completion_rate"].value == pytest.approx(2 / 3, abs=1e-3)
        assert result["disputes"].value == 1

    def test_vendor_churn(self):
        stayed = _published(40)
        left = _published(45)
        left.closed_at = timezone.now() - timedelta(days=35)
        left.save(update_fields=["closed_at"])
        result = {k.key: k for k in kpis.compute(timezone.localdate(), 28)}
        assert result["vendor_churn"].sample == 2
        assert result["vendor_churn"].value == 0.5
        assert stayed.vendor_id != left.vendor_id

    def test_no_data_is_not_a_failure(self):
        result = {k.key: k for k in kpis.compute(timezone.localdate(), 7)}
        assert result["fill_rate_14d"].status == "no_data"
        assert result["average_rating"].value is None

    def test_the_daily_snapshot(self):
        kpis.snapshot()
        kpis.snapshot()  # rerunning replaces, never duplicates
        snapshot = KpiSnapshot.objects.get()
        assert snapshot.window_days == 28
        assert set(snapshot.metrics) >= {"applications_per_gig", "no_show_rate", "vendor_churn"}


class TestDashboard:
    def test_ops_and_finance_see_it_support_doesnt(self):
        _published(20)
        for role, expected in [("ops", 200), ("finance", 200), ("trust", 200), ("support", 403)]:
            browser = Client()
            browser.force_login(AdminUserFactory(roles=[role]))
            response = browser.get(reverse("admin:analytics_kpis"), {"days": 28})
            assert response.status_code == expected, role

    def test_it_renders_every_kpi_with_its_target(self):
        browser = Client()
        browser.force_login(AdminUserFactory(roles=["ops"]))
        kpis.snapshot()
        page = browser.get(reverse("admin:analytics_kpis")).content.decode()
        for label in [
            "Applications per gig",
            "Gigs filled within 14 days",
            "No-shows",
            "Host churn",
        ]:
            assert label in page
        assert "Target ≥ 8" in page and "Target &lt; 5.0%" in page


def test_vendors_count_too():
    vendor = VendorFactory()
    agree(vendor)
    assert (
        send(vendor, {"name": "gig_builder_step", "props": {"step": 3}}, platform="web").json()[
            "accepted"
        ]
        == 1
    )
    assert AnalyticsEvent.objects.get().role == "vendor"
