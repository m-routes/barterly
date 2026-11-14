import io
import json
import urllib.error
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import TalentFactory, VendorFactory
from apps.geo.distance import bounding_box, haversine_m, offset
from apps.geo.geocoders import (
    GeocoderUnavailable,
    NominatimGeocoder,
    RateLimiter,
    get_geocoder,
)
from apps.geo.models import GeocodeResult
from apps.geo.services import geocode, normalize_query
from apps.verification.tests.factories import client_for


class TestDistance:
    def test_haversine_and_offset_agree(self):
        lat, lng = offset(32.0, 77.0, north_m=300, east_m=400)
        assert haversine_m(32.0, 77.0, lat, lng) == pytest.approx(500, abs=1)

    def test_bounding_box_contains_the_circle(self):
        box = bounding_box(32.0, 77.0, 1000)
        for north, east in [(1000, 0), (-1000, 0), (0, 1000), (0, -1000)]:
            lat, lng = offset(32.0, 77.0, north_m=north * 0.999, east_m=east * 0.999)
            assert box.min_lat <= lat <= box.max_lat and box.min_lng <= lng <= box.max_lng


def test_queries_are_normalized():
    assert normalize_query("  Old  Manali Road ,Manali,  HP ") == "old manali road, manali, hp"


@pytest.mark.django_db
class TestCachedGeocode:
    def test_each_query_reaches_the_geocoder_once(self):
        first = geocode("Old Manali Road, Manali")
        again = geocode("old manali road ,  MANALI")
        assert first.pk == again.pk and again.hits == 1
        assert first.found and float(first.latitude) == pytest.approx(32.2432)
        assert get_geocoder().calls == ["old manali road, manali"]

    def test_not_found_is_cached_then_retried_after_a_month(self):
        miss = geocode("Nowhere Lane, Atlantis")
        assert not miss.found and miss.latitude is None
        geocode("Nowhere Lane, Atlantis")
        assert len(get_geocoder().calls) == 1
        GeocodeResult.objects.filter(pk=miss.pk).update(
            fetched_at=timezone.now() - timedelta(days=31)
        )
        geocode("Nowhere Lane, Atlantis")
        assert len(get_geocoder().calls) == 2

    def test_too_short_is_refused_without_a_lookup(self):
        with pytest.raises(ValueError):
            geocode("Goa")
        assert get_geocoder().calls == []


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.django_db
class TestNominatim:
    def make(self, rows=None, error=None):
        sent = []

        def opener(request, timeout):
            sent.append((request, timeout))
            if error:
                raise error
            return FakeResponse(json.dumps(rows or []).encode())

        return NominatimGeocoder(opener=opener), sent

    def test_request_identifies_us_and_limits_to_india(self, settings):
        settings.NOMINATIM_EMAIL = "ops@example.org"
        geocoder, sent = self.make(
            [
                {
                    "lat": "15.5527",
                    "lon": "73.7517",
                    "display_name": "Anjuna, Goa",
                    "address": {"village": "Anjuna", "state": "Goa", "postcode": "403509"},
                }
            ]
        )
        hit = geocoder.geocode("anjuna, goa")
        request, timeout = sent[0]
        assert request.get_header("User-agent") == settings.NOMINATIM_USER_AGENT
        assert "countrycodes=in" in request.full_url and "limit=1" in request.full_url
        assert "email=ops%40example.org" in request.full_url
        assert timeout == settings.GEOCODER_TIMEOUT_SECONDS
        assert (hit.latitude, hit.city, hit.state, hit.postcode) == (
            15.5527,
            "Anjuna",
            "Goa",
            "403509",
        )

    def test_no_match_and_failures(self):
        geocoder, _ = self.make([])
        assert geocoder.geocode("x road") is None
        geocoder, _ = self.make(error=urllib.error.URLError("down"))
        with pytest.raises(GeocoderUnavailable):
            geocoder.geocode("y road")

    def test_one_request_per_second(self):
        geocoder, sent = self.make([])
        geocoder.geocode("first road")
        clock = iter(range(100))
        geocoder.limiter = RateLimiter(
            "geo:nominatim:slot", max_wait=2, sleep=lambda s: None, clock=lambda: next(clock)
        )
        with pytest.raises(GeocoderUnavailable, match="busy"):
            geocoder.geocode("second road")  # the first call's slot is still held
        assert len(sent) == 1


@pytest.mark.django_db
class TestGeocodeEndpoint:
    def test_vendors_can_find_an_address(self):
        response = client_for(VendorFactory()).post(
            "/api/v1/geo/geocode/", {"query": "Mall Road, Manali"}, format="json"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["found"] and body["state"] == "Himachal Pradesh"

    def test_not_for_talent_and_short_queries_rejected(self):
        assert (
            client_for(TalentFactory())
            .post("/api/v1/geo/geocode/", {"query": "Mall Road, Manali"}, format="json")
            .status_code
            == 403
        )
        short = client_for(VendorFactory()).post(
            "/api/v1/geo/geocode/", {"query": "ab"}, format="json"
        )
        assert short.status_code == 400

    def test_geocoder_down_is_503(self, settings):
        settings.GEOCODER = "apps.geo.tests.test_geo.BrokenGeocoder"
        from apps.geo import geocoders

        geocoders._build.cache_clear()
        response = client_for(VendorFactory()).post(
            "/api/v1/geo/geocode/", {"query": "Mall Road, Manali"}, format="json"
        )
        assert response.status_code == 503
        assert response.json()["code"] == "geocoder_unavailable"
        assert not GeocodeResult.objects.exists()


class BrokenGeocoder:
    name = "broken"

    def geocode(self, query):
        raise GeocoderUnavailable("down")
