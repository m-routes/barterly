from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.tests.factories import VendorFactory
from apps.gigs.constants import CompensationModel, GigStatus, RoleTemplate, StayType
from apps.gigs.tests.factories import GigFactory, in_days
from apps.profiles.tests.factories import SkillFactory, TalentProfileFactory
from apps.properties.tests.factories import PropertyFactory, add_photos
from apps.verification.constants import BadgeKind, CaseStatus
from apps.verification.models import Badge
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
URL = "/api/v1/gigs/"
GOA = {"latitude": Decimal("15.552700"), "longitude": Decimal("73.751700")}


def live(minutes_ago=0, **kwargs):
    gig = GigFactory(status=GigStatus.LIVE, **kwargs)
    gig.published_at = timezone.now() - timedelta(minutes=minutes_ago)
    gig.save(update_fields=["published_at"])
    return gig


@pytest.fixture
def talent():
    return TalentProfileFactory(languages=["en", "hi"], instagram_followers=2000).user


def ids(response) -> list[str]:
    assert response.status_code == 200, response.json()
    return [g["id"] for g in response.json()["results"]]


class TestHardFilters:
    def test_only_live_gigs_still_taking_applications(self, talent):
        shown = live()
        GigFactory(status=GigStatus.DRAFT)
        GigFactory(status=GigStatus.PAUSED)
        expired = live()
        type(expired).objects.filter(pk=expired.pk).update(apply_by=in_days(-1))
        gone = live()
        gone.property.deleted_at = timezone.now()
        gone.property.save()
        assert ids(client_for(talent).get(URL)) == [str(shown.pk)]

    def test_eligibility_languages_and_followers(self, talent):
        ok = live(languages=["hi", "ta"], min_followers=1000)
        live(languages=["fr"])  # no shared language
        live(min_followers=5000)  # more followers than the talent has
        open_to_all = live()
        assert set(ids(client_for(talent).get(URL))) == {str(ok.pk), str(open_to_all.pk)}

    def test_unknown_followers_count_as_zero(self):
        newbie = TalentProfileFactory(instagram_followers=None).user
        live(min_followers=10)
        assert ids(client_for(newbie).get(URL)) == []

    def test_simple_filters(self, talent):
        barter = live(
            compensation_model=CompensationModel.BARTER,
            role_template=RoleTemplate.CONTENT_CREATOR,
            deliverables=[{"type": "instagram_reel", "quantity": 1}],
            stay_type=StayType.PRIVATE_ROOM,
            min_stay_days=14,
            start_date=in_days(40),
        )
        volunteer = live(property=PropertyFactory(city="Goa", women_friendly=True, **GOA))
        client = client_for(talent)
        assert ids(client.get(URL, {"compensation_model": "barter,paid"})) == [str(barter.pk)]
        assert ids(client.get(URL, {"role": "content_creator"})) == [str(barter.pk)]
        assert ids(client.get(URL, {"stay_type": "private_room"})) == [str(barter.pk)]
        assert ids(client.get(URL, {"city": "goa"})) == [str(volunteer.pk)]
        assert ids(client.get(URL, {"women_friendly": "true"})) == [str(volunteer.pk)]
        assert ids(client.get(URL, {"min_stay": 7})) == [str(volunteer.pk)]
        window = {"start_from": str(in_days(35)), "start_to": str(in_days(45))}
        assert ids(client.get(URL, window)) == [str(barter.pk)]

    def test_radius_uses_the_approximate_location(self, talent):
        manali = live()
        live(property=PropertyFactory(**GOA))
        near = {"latitude": 32.2432, "longitude": 77.1892, "radius_km": 5}
        assert ids(client_for(talent).get(URL, near)) == [str(manali.pk)]

    def test_verified_hosts_only(self, talent):
        prop = PropertyFactory()
        verified = live(property=prop)
        prop.verification_status = CaseStatus.APPROVED
        prop.save()
        live(property=PropertyFactory(verification_status=CaseStatus.APPROVED))  # no ID badge
        Badge.objects.create(
            user=prop.vendor,
            kind=BadgeKind.ID_VERIFIED,
            granted_at=timezone.now(),
            grant_reason="x",
        )
        response = client_for(talent).get(URL, {"verified_hosts": "true"})
        assert ids(response) == [str(verified.pk)]
        assert response.json()["results"][0]["host_verified"] is True

    def test_keyword_full_text(self, talent):
        mural = live(title="Paint a mural in the cafe", description="Bright walls, big brushes.")
        live(title="Front desk", description="Check guests in.")
        assert ids(client_for(talent).get(URL, {"q": "murals"})) == [str(mural.pk)]  # stemmed
        assert ids(client_for(talent).get(URL, {"q": '"big brushes"'})) == [str(mural.pk)]


class TestSortingAndScore:
    def test_best_fit_ranks_skill_matches_first_and_explains_it(self):
        cooking = SkillFactory(slug="cooking")
        talent = TalentProfileFactory(languages=["en"])
        talent.skills.set([cooking])
        plain = live(minutes_ago=1)
        match = live(minutes_ago=5)
        match.skills.set([cooking])
        response = client_for(talent.user).get(URL)
        assert ids(response) == [str(match.pk), str(plain.pk)]
        fit = response.json()["results"][0]["fit"]
        assert fit["score"] > 50
        assert fit["breakdown"]["skill_match"]["reason"] == "1 of 1 skills match."
        assert fit["breakdown"]["reliability"]["neutral"] is True

    def test_newest_start_date_and_distance(self, talent):
        old = live(minutes_ago=60, start_date=in_days(25))
        new = live(
            minutes_ago=1,
            property=PropertyFactory(**GOA),
            start_date=in_days(50),
            end_date=in_days(70),
        )
        client = client_for(talent)
        assert ids(client.get(URL, {"sort": "newest"})) == [str(new.pk), str(old.pk)]
        assert ids(client.get(URL, {"sort": "start_date"})) == [str(old.pk), str(new.pk)]
        from_goa = {"sort": "distance", "latitude": 15.55, "longitude": 73.75}
        response = client.get(URL, from_goa)
        assert ids(response) == [str(new.pk), str(old.pk)]
        assert response.json()["results"][0]["distance_km"] < 2
        assert client.get(URL, {"sort": "distance"}).status_code == 400  # needs a point

    @pytest.mark.parametrize("sort", ["best_fit", "newest", "start_date"])
    def test_cursor_pages_cover_everything_once(self, talent, sort, settings):
        settings.DISCOVERY_PAGE_SIZE = 2
        made = {str(live(minutes_ago=i, start_date=in_days(25 + i % 3)).pk) for i in range(5)}
        client, seen, params = client_for(talent), [], {"sort": sort}
        while True:
            body = client.get(URL, params).json()
            seen += [g["id"] for g in body["results"]]
            if not body["next_cursor"]:
                break
            params = {"sort": sort, "cursor": body["next_cursor"]}
        assert len(seen) == 5 and set(seen) == made

    def test_bad_cursors(self, talent):
        client = client_for(talent)
        assert client.get(URL, {"cursor": "nope"}).status_code == 400
        live()
        live()
        from apps.discovery.services import encode_cursor

        other_sort = encode_cursor("newest", timezone.now(), "x")
        assert client.get(URL, {"cursor": other_sort}).status_code == 400


def test_query_count_does_not_grow_with_results(talent):
    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = client_for(talent).get(URL)
        assert response.status_code == 200
        return len(ctx.captured_queries), len(response.json()["results"])

    vendor = VendorFactory()
    for _ in range(2):
        gig = live(property=PropertyFactory(vendor=vendor))
        add_photos(gig.property)
        gig.skills.set([SkillFactory()])
    few, shown = count_queries()
    assert shown == 2
    for _ in range(6):
        gig = live(property=PropertyFactory(vendor=vendor))
        add_photos(gig.property)
        gig.skills.set([SkillFactory()])
    many, shown = count_queries()
    assert shown == 8
    # Profile, profile skills, gigs (with property and the ID badge), gig skills, photos.
    assert few == many == 5


def test_only_talent_can_discover():
    assert client_for(VendorFactory()).get(URL).status_code == 403
