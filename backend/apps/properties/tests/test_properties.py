from decimal import Decimal

import pytest
import yaml
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.common.models import AuditLog
from apps.geo.distance import haversine_m
from apps.geo.geocoders import get_geocoder
from apps.media.policy import Kind
from apps.properties.models import (
    APPROX_MAX_M,
    APPROX_MIN_M,
    Property,
    approximate_point,
)
from apps.properties.tests.factories import PropertyFactory, add_photos
from apps.verification.constants import BadgeKind, CaseStatus
from apps.verification.services.cases import Decision, active_badge_kinds, decide
from apps.verification.tests.factories import PIN, MediaFileFactory, client_for

pytestmark = pytest.mark.django_db

BASE = "/api/v1/properties"
NEW = {
    "name": "Pine Hostel",
    "property_type": "hostel",
    "address": "Old Manali Road",
    "city": "Manali",
    "state": "Himachal Pradesh",
    "amenities": ["wifi", "hot_water", "wifi"],
    "house_rules": [" No smoking indoors ", "Quiet after 11 pm"],
    "women_friendly": True,
}


class TestOwnerCrud:
    def test_create_geocodes_the_address_once_and_needs_confirmation(self):
        vendor = VendorFactory()
        response = client_for(vendor).post(f"{BASE}/", NEW, format="json")
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["latitude"] == "32.243200" and body["location_confirmed"] is False
        assert body["amenities"] == ["wifi", "hot_water"]
        assert body["house_rules"] == ["No smoking indoors", "Quiet after 11 pm"]
        assert body["verification_status"] == "not_started"
        assert get_geocoder().calls == ["old manali road, manali, himachal pradesh, india"]
        assert AuditLog.objects.filter(action="property.created").exists()

        prop_id = body["id"]
        confirmed = client_for(vendor).patch(
            f"{BASE}/{prop_id}/", {"location_confirmed": True}, format="json"
        )
        assert confirmed.json()["location_confirmed"] is True

        # A cosmetic edit doesn't geocode again or un-confirm the pin.
        client_for(vendor).patch(f"{BASE}/{prop_id}/", {"women_friendly": False}, format="json")
        assert len(get_geocoder().calls) == 1
        assert Property.objects.get(pk=prop_id).location_confirmed

    def test_moving_the_pin_or_changing_the_address_unconfirms(self):
        prop = PropertyFactory()
        client = client_for(prop.vendor)
        client.patch(
            f"{BASE}/{prop.pk}/", {"latitude": "32.25", "longitude": "77.19"}, format="json"
        )
        prop.refresh_from_db()
        assert prop.location_confirmed is False and prop.latitude == Decimal("32.25")

        client.patch(f"{BASE}/{prop.pk}/", {"location_confirmed": True}, format="json")
        client.patch(f"{BASE}/{prop.pk}/", {"address": "Club House Road"}, format="json")
        prop.refresh_from_db()
        assert prop.location_confirmed is False

    def test_validation(self):
        client = client_for(VendorFactory())
        bad = {**NEW, "amenities": ["helipad"], "state": "Atlantis"}
        response = client.post(f"{BASE}/", bad, format="json")
        assert response.status_code == 400
        assert {"amenities", "state"} <= set(response.json()["details"])
        half_pin = client.post(f"{BASE}/", {**NEW, "latitude": "32.1"}, format="json")
        assert half_pin.status_code == 400
        # Not geocodable (the fake knows no such place), so there's no pin to confirm.
        unpinned = {
            **NEW,
            "address": "Nowhere",
            "city": "Atlantis",
            "state": "Kerala",
            "location_confirmed": True,
        }
        response = client.post(f"{BASE}/", unpinned, format="json")
        assert response.status_code == 400
        assert "location_confirmed" in response.json()["details"]

    def test_geocoder_down_still_saves_without_a_pin(self, settings):
        from apps.geo import geocoders

        settings.GEOCODER = "apps.geo.tests.test_geo.BrokenGeocoder"
        geocoders._build.cache_clear()
        response = client_for(VendorFactory()).post(f"{BASE}/", NEW, format="json")
        assert response.status_code == 201
        assert response.json()["latitude"] is None
        assert response.json()["location_confirmed"] is False

    def test_owner_only(self):
        prop = PropertyFactory()
        other = client_for(VendorFactory())
        assert other.get(f"{BASE}/{prop.pk}/").status_code == 404
        assert other.patch(f"{BASE}/{prop.pk}/", {"name": "Mine"}, format="json").status_code == 404
        assert other.get(f"{BASE}/").json()["results"] == []
        assert client_for(TalentFactory()).get(f"{BASE}/").status_code == 403
        assert APIClient().get(f"{BASE}/").status_code == 401

    def test_delete_is_soft_and_withdraws_verification(self):
        prop = PropertyFactory()
        add_photos(prop)
        client = client_for(prop.vendor)
        case = client.post(f"{BASE}/{prop.pk}/verification/")
        decide(case.json()["id"], Decision.APPROVE, reviewer=AdminUserFactory())
        assert BadgeKind.PROPERTY_VERIFIED in active_badge_kinds(prop.vendor)

        assert client.delete(f"{BASE}/{prop.pk}/").status_code == 204
        assert not Property.objects.filter(pk=prop.pk).exists()
        gone = Property.all_objects.get(pk=prop.pk)
        assert gone.is_deleted and gone.verification_status == CaseStatus.EXPIRED
        assert BadgeKind.PROPERTY_VERIFIED not in active_badge_kinds(prop.vendor)
        assert AuditLog.objects.filter(action="property.deleted").exists()
        assert client.get(f"{BASE}/{prop.pk}/public/").status_code == 404


class TestPhotos:
    def test_add_and_remove(self):
        prop = PropertyFactory()
        client = client_for(prop.vendor)
        media = MediaFileFactory(owner=prop.vendor)
        added = client.post(
            f"{BASE}/{prop.pk}/photos/",
            {
                "media_id": str(media.pk),
                "caption": "Dorm",
                "latitude": "32.2433",
                "longitude": "77.1892",
            },
            format="json",
        )
        assert added.status_code == 201, added.json()
        assert added.json()["position"] == 0
        again = client.post(f"{BASE}/{prop.pk}/photos/", {"media_id": str(media.pk)}, format="json")
        assert again.status_code == 400

        photo_id = added.json()["id"]
        assert client.delete(f"{BASE}/{prop.pk}/photos/{photo_id}/").status_code == 204
        assert prop.photos.count() == 0

    @pytest.mark.parametrize(
        "make",
        [
            lambda v: MediaFileFactory(),
            lambda v: MediaFileFactory(owner=v, kind=Kind.DOCUMENT),
        ],
        ids=["not-mine", "not-a-photo"],
    )
    def test_only_my_photo_uploads(self, make):
        prop = PropertyFactory()
        media = make(prop.vendor)
        response = client_for(prop.vendor).post(
            f"{BASE}/{prop.pk}/photos/", {"media_id": str(media.pk)}, format="json"
        )
        assert response.status_code == 400


class TestVerificationSubmit:
    def test_needs_three_photos(self):
        prop = PropertyFactory()
        add_photos(prop, n=2)
        client = client_for(prop.vendor)
        response = client.post(f"{BASE}/{prop.pk}/verification/")
        assert response.status_code == 400
        assert "at least 3 photos" in str(response.json()["details"])

        add_photos(prop, n=1)
        response = client.post(f"{BASE}/{prop.pk}/verification/")
        assert response.status_code == 200
        assert response.json()["property_id"] == str(prop.pk)
        assert response.json()["status"] == "submitted"
        assert client.get(f"{BASE}/{prop.pk}/").json()["verification_status"] == "submitted"

    def test_others_cannot_submit(self):
        prop = PropertyFactory()
        add_photos(prop)
        assert (
            client_for(VendorFactory()).post(f"{BASE}/{prop.pk}/verification/").status_code == 404
        )


class TestPublicView:
    def test_shows_only_an_approximate_location(self):
        prop = PropertyFactory()
        add_photos(prop)
        body = APIClient().get(f"{BASE}/{prop.pk}/public/").json()
        assert body["exact_location"] is None
        assert "address" not in body and "latitude" not in body
        approx = body["approximate_location"]
        assert approx["radius_m"] == 1000
        away = haversine_m(
            PIN["latitude"], PIN["longitude"], approx["latitude"], approx["longitude"]
        )
        assert APPROX_MIN_M - 20 <= away <= APPROX_MAX_M + 20
        assert body["verified"] is False
        assert len(body["photos"]) == 3

        # Stable: asking again (or by someone else) gives the same point.
        again = client_for(VendorFactory()).get(f"{BASE}/{prop.pk}/public/").json()
        assert again["approximate_location"] == approx
        assert again["exact_location"] is None

    def test_owner_and_admin_see_the_exact_location(self):
        prop = PropertyFactory()
        for viewer in (prop.vendor, AdminUserFactory()):
            exact = client_for(viewer).get(f"{BASE}/{prop.pk}/public/").json()["exact_location"]
            assert exact["address"] == prop.address and exact["latitude"] == PIN["latitude"]

    def test_unservable_photos_are_hidden(self):
        prop = PropertyFactory()
        photos = add_photos(prop)
        photos[0].media.status = "processing"
        photos[0].media.save()
        body = APIClient().get(f"{BASE}/{prop.pk}/public/").json()
        assert len(body["photos"]) == 2


class TestNearby:
    def test_within_radius_orders_by_distance_on_the_approximate_point(self):
        near = PropertyFactory()
        far = PropertyFactory(latitude=Decimal("32.30"), longitude=Decimal("77.19"))
        PropertyFactory(latitude=Decimal("15.55"), longitude=Decimal("73.75"))  # Goa
        PropertyFactory(latitude=None, longitude=None, location_confirmed=False)

        found = list(Property.objects.within_radius(PIN["latitude"], PIN["longitude"], 10_000))
        assert [p.pk for p in found] == [near.pk, far.pk]
        assert found[0].distance_m < 1000

        exact = Property.objects.within_radius(PIN["latitude"], PIN["longitude"], 50, public=False)
        assert [p.pk for p in exact] == [near.pk]

    def test_approximate_point_is_none_without_a_pin(self):
        prop = PropertyFactory.build(latitude=None, longitude=None)
        assert approximate_point(prop) == (None, None)


def test_every_endpoint_is_in_the_openapi_schema(tmp_path):
    out = tmp_path / "schema.yaml"
    call_command("spectacular", "--file", str(out), "--validate", "--fail-on-warn")
    paths = yaml.safe_load(out.read_text())["paths"]
    assert {p for p in paths if p.startswith(("/api/v1/properties/", "/api/v1/geo/"))} == {
        "/api/v1/properties/",
        "/api/v1/properties/{property_id}/",
        "/api/v1/properties/{property_id}/photos/",
        "/api/v1/properties/{property_id}/photos/{photo_id}/",
        "/api/v1/properties/{property_id}/verification/",
        "/api/v1/properties/{property_id}/public/",
        "/api/v1/geo/geocode/",
    }
