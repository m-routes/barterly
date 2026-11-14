from io import StringIO

import pytest
import yaml
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.gigs.constants import GigStatus
from apps.gigs.tests.factories import GigFactory, in_days
from apps.profiles.tests.factories import SkillFactory
from apps.properties.tests.factories import PropertyFactory
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
BASE = "/api/v1/gigs"


def new_gig(prop, **overrides):
    return {
        "property": str(prop.pk),
        "title": "Content creator for monsoon season",
        "description": "Two reels a week about the hostel and the valley.",
        "role_template": "content_creator",
        "compensation_model": "barter",
        "start_date": str(in_days(30)),
        "duration_days": 21,
        "apply_by": str(in_days(15)),
        "slots": 1,
        "hours_per_day": 4,
        "days_per_week": 5,
        "stay_type": "private_room",
        "meals": "breakfast",
        "deliverables": [{"type": "instagram_reel", "quantity": 6, "notes": "Vertical, 30s"}],
        "skills": [SkillFactory(slug="photography").slug],
        "languages": ["en", "hi"],
        "min_followers": 5000,
        "screening_questions": ["Link your best travel reel."],
        **overrides,
    }


def test_vendor_creates_submits_and_admin_approves():
    prop = PropertyFactory()
    vendor = client_for(prop.vendor)
    created = vendor.post(f"{BASE}/", new_gig(prop), format="json")
    assert created.status_code == 201, created.json()
    body = created.json()
    assert body["status"] == "draft" and body["min_age"] == 18
    assert body["skills"] == ["photography"]
    assert body["deliverables"] == [
        {"type": "instagram_reel", "quantity": 6, "notes": "Vertical, 30s"}
    ]
    gig_id = body["id"]

    submitted = vendor.post(f"{BASE}/{gig_id}/status/", {"status": "in_review"}, format="json")
    assert submitted.status_code == 200 and submitted.json()["status"] == "in_review"

    admin = client_for(AdminUserFactory())
    queue = admin.get(f"{BASE}/admin/").json()["results"]
    assert [g["id"] for g in queue] == [gig_id]
    sent_back = admin.post(f"{BASE}/{gig_id}/status/", {"status": "draft"}, format="json")
    assert sent_back.status_code == 400  # needs a reason
    approved = admin.post(f"{BASE}/{gig_id}/status/", {"status": "live"}, format="json")
    assert approved.status_code == 200 and approved.json()["status"] == "live"

    self_approve = GigFactory(property=PropertyFactory(vendor=prop.vendor))
    vendor.post(f"{BASE}/{self_approve.pk}/status/", {"status": "in_review"}, format="json")
    refused = vendor.post(f"{BASE}/{self_approve.pk}/status/", {"status": "live"}, format="json")
    assert refused.status_code == 409


def test_rules_are_enforced_on_submit_with_field_errors():
    gig = GigFactory(hours_per_day=6, days_per_week=6, meals="")
    response = client_for(gig.vendor).post(
        f"{BASE}/{gig.pk}/status/", {"status": "in_review"}, format="json"
    )
    assert response.status_code == 400
    assert "meals" in response.json()["details"]


def test_field_limits_on_create():
    prop = PropertyFactory()
    response = client_for(prop.vendor).post(
        f"{BASE}/", new_gig(prop, hours_per_day=8, days_per_week=7, slots=0), format="json"
    )
    assert response.status_code == 400
    assert {"hours_per_day", "days_per_week", "slots"} <= set(response.json()["details"])


def test_property_must_be_mine():
    mine, theirs = PropertyFactory(), PropertyFactory()
    response = client_for(mine.vendor).post(f"{BASE}/", new_gig(theirs), format="json")
    assert response.status_code == 400 and "property" in response.json()["details"]


def test_editing_live_pay_goes_back_to_review():
    gig = GigFactory(status=GigStatus.LIVE)
    response = client_for(gig.vendor).patch(
        f"{BASE}/{gig.pk}/", {"start_date": str(in_days(35))}, format="json"
    )
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "in_review"
    assert "start date" in response.json()["status_reason"]


def test_access():
    gig = GigFactory()
    other_vendor = client_for(VendorFactory())
    assert other_vendor.get(f"{BASE}/{gig.pk}/").status_code == 404
    assert (
        other_vendor.post(
            f"{BASE}/{gig.pk}/status/", {"status": "in_review"}, format="json"
        ).status_code
        == 404
    )
    assert client_for(TalentFactory()).get(f"{BASE}/mine/").status_code == 403
    assert client_for(TalentFactory()).post(f"{BASE}/", {}, format="json").status_code == 403
    assert client_for(gig.vendor).get(f"{BASE}/").status_code == 403  # discovery is for talent
    assert APIClient().get(f"{BASE}/mine/").status_code == 401
    admin = client_for(AdminUserFactory())
    assert admin.get(f"{BASE}/{gig.pk}/").status_code == 200
    assert admin.patch(f"{BASE}/{gig.pk}/", {"title": "x"}, format="json").status_code == 403
    assert client_for(gig.vendor).get(f"{BASE}/admin/").status_code == 403


def test_list_filters_by_status():
    gig = GigFactory()
    GigFactory(property=PropertyFactory(vendor=gig.vendor), status=GigStatus.LIVE)
    body = client_for(gig.vendor).get(f"{BASE}/mine/", {"status": "live"}).json()
    assert [g["status"] for g in body["results"]] == ["live"]


def test_close_expired_gigs_command():
    out = StringIO()
    call_command("close_expired_gigs", stdout=out)
    assert "Closed 0" in out.getvalue()


def test_every_endpoint_is_in_the_openapi_schema(tmp_path):
    out = tmp_path / "schema.yaml"
    call_command("spectacular", "--file", str(out), "--validate", "--fail-on-warn")
    paths = yaml.safe_load(out.read_text())["paths"]
    assert {p for p in paths if p.startswith("/api/v1/gigs/")} == {
        "/api/v1/gigs/",
        "/api/v1/gigs/mine/",
        "/api/v1/gigs/saved-searches/",
        "/api/v1/gigs/saved-searches/{search_id}/",
        "/api/v1/gigs/admin/",
        "/api/v1/gigs/{gig_id}/",
        "/api/v1/gigs/{gig_id}/status/",
    }
