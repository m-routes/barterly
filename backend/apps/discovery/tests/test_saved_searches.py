from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.tests.factories import TalentFactory
from apps.discovery.alerts import ALERT_KIND, run_alerts
from apps.discovery.models import MAX_SAVED_SEARCHES, SavedSearch, SavedSearchMatch
from apps.gigs.constants import CompensationModel, GigStatus
from apps.gigs.tests.factories import GigFactory
from apps.notifications.models import Notification
from apps.profiles.tests.factories import TalentProfileFactory
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
URL = "/api/v1/gigs/saved-searches/"


def publish(**kwargs):
    gig = GigFactory(status=GigStatus.LIVE, **kwargs)
    gig.published_at = timezone.now()
    gig.save(update_fields=["published_at"])
    return gig


@pytest.fixture
def talent():
    return TalentProfileFactory(languages=["en"]).user


class TestApi:
    def test_create_validates_params_and_lists_mine(self, talent):
        client = client_for(talent)
        created = client.post(
            URL,
            {
                "name": "Goa barter",
                "params": {
                    "compensation_model": ["barter"],
                    "city": "Goa",
                    "start_from": "2027-01-01",
                },
            },
            format="json",
        )
        assert created.status_code == 201, created.json()
        assert created.json()["params"] == {
            "compensation_model": ["barter"],
            "city": "Goa",
            "start_from": "2027-01-01",
            "sort": "best_fit",
        }
        bad = client.post(URL, {"name": "x", "params": {"radius_km": 5}}, format="json")
        assert bad.status_code == 400
        assert [s["name"] for s in client.get(URL).json()] == ["Goa barter"]
        assert client_for(TalentFactory()).get(URL).json() == []

    def test_edit_and_delete(self, talent):
        search = SavedSearch.objects.create(
            talent=talent, name="All", params={}, last_checked_at=timezone.now()
        )
        client = client_for(talent)
        response = client.patch(f"{URL}{search.pk}/", {"alerts_enabled": False}, format="json")
        assert response.json()["alerts_enabled"] is False
        assert client.delete(f"{URL}{search.pk}/").status_code == 204
        assert client_for(TalentFactory()).get(f"{URL}{search.pk}/").status_code == 404

    def test_limit(self, talent):
        for i in range(MAX_SAVED_SEARCHES):
            SavedSearch.objects.create(
                talent=talent, name=str(i), params={}, last_checked_at=timezone.now()
            )
        response = client_for(talent).post(URL, {"name": "one more", "params": {}}, format="json")
        assert response.status_code == 400


class TestAlerts:
    def test_new_matches_queue_one_notification_and_never_repeat(self, talent):
        before = publish()  # published before the search existed: not "new"
        search = SavedSearch.objects.create(
            talent=talent,
            name="Barter",
            params={"compensation_model": ["barter"]},
            last_checked_at=timezone.now(),
        )
        barter = publish(
            compensation_model=CompensationModel.BARTER,
            deliverables=[{"type": "instagram_reel", "quantity": 1}],
        )
        publish()  # volunteer: doesn't match the filter

        counts = run_alerts(now=timezone.now() + timedelta(seconds=1))
        assert counts == {"searches": 1, "matches": 1, "notifications": 1}
        match = SavedSearchMatch.objects.get()
        assert match.gig == barter and match.breakdown["skill_match"]["neutral"] is True
        note = Notification.objects.get()
        assert note.user == talent and note.kind == ALERT_KIND and note.status == "queued"
        assert note.payload["count"] == 1 and note.payload["gigs"][0]["id"] == str(barter.pk)
        assert note.payload["saved_search_id"] == str(search.pk)

        again = run_alerts(now=timezone.now() + timedelta(seconds=2))
        assert again["matches"] == 0 and Notification.objects.count() == 1
        assert not SavedSearchMatch.objects.filter(gig=before).exists()

    def test_alerts_respect_eligibility_and_the_switch(self, talent):
        search = SavedSearch.objects.create(
            talent=talent, name="All", params={}, last_checked_at=timezone.now()
        )
        publish(languages=["fr"])  # talent doesn't speak French
        assert run_alerts(now=timezone.now() + timedelta(seconds=1))["matches"] == 0
        search.alerts_enabled = False
        search.save()
        publish()
        assert run_alerts(now=timezone.now() + timedelta(seconds=1))["searches"] == 0

    def test_command(self):
        out = StringIO()
        call_command("run_search_alerts", stdout=out)
        assert "Checked 0 search(es)" in out.getvalue()
