import json

import pytest
import yaml
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import AdminUserFactory, VendorFactory
from apps.applications.models import Application
from apps.applications.services import transition
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.gigs.tests.factories import in_days
from apps.verification.tests.factories import MediaFileFactory, client_for

pytestmark = pytest.mark.django_db


def body(**overrides):
    d = dates()
    return {
        "pitch": "Three seasons at hostels in Goa.",
        "answers": [],
        "proposed_start": str(d["proposed_start"]),
        "proposed_end": str(d["proposed_end"]),
        "attachments": [],
        **overrides,
    }


def apply_via_api(talent, gig, **overrides):
    return client_for(talent).post(
        f"/api/v1/gigs/{gig.pk}/applications/", body(**overrides), format="json"
    )


class TestApply:
    def test_created_with_attachments(self):
        talent, gig = eligible_talent(), live_gig()
        video = MediaFileFactory(owner=talent, kind="video", content_type="video/mp4")
        response = apply_via_api(
            talent,
            gig,
            attachments=[
                {"kind": "video", "media_id": str(video.pk), "title": "Showreel"},
                {"kind": "link", "url": "https://example.org/cv.pdf", "title": "CV"},
            ],
        )
        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["status"] == "applied" and data["gig_title"] == gig.title
        assert [a["kind"] for a in data["attachments"]] == ["video", "link"]
        assert data["attachments"][1]["url"] == "https://example.org/cv.pdf"
        assert 0 <= data["fit"]["score"] <= 100

    def test_blocked_lists_every_reason(self):
        gig = live_gig(screening_questions=["Why?"], min_followers=50_000)
        response = apply_via_api(eligible_talent(), gig)
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "application_blocked"
        codes = {r["code"] for r in data["details"]["reasons"]}
        assert codes == {"not_enough_followers", "answers_missing"}
        assert all(r["message"] for r in data["details"]["reasons"])

    def test_bad_attachments_and_limits_are_400(self):
        talent, gig = eligible_talent(), live_gig()
        http_link = [{"kind": "link", "url": "http://example.org"}]
        assert apply_via_api(talent, gig, attachments=http_link).status_code == 400
        nine = [{"kind": "link", "url": f"https://example.org/{i}"} for i in range(9)]
        assert apply_via_api(talent, gig, attachments=nine).status_code == 400
        upload_without_media = [{"kind": "photo"}]
        assert apply_via_api(talent, gig, attachments=upload_without_media).status_code == 400

    def test_vendors_cannot_apply(self):
        assert apply_via_api(VendorFactory(), live_gig()).status_code == 403


class TestVendorViews:
    def setup_applicants(self, n):
        gig = live_gig()
        for _ in range(n):
            talent = eligible_talent()
            photo = MediaFileFactory(owner=talent)
            response = apply_via_api(
                talent, gig, attachments=[{"kind": "photo", "media_id": str(photo.pk)}]
            )
            assert response.status_code == 201
        return gig

    def test_list_sorted_by_fit_with_filters(self):
        gig = self.setup_applicants(3)
        Application.objects.filter(gig=gig).update(fit_score=40)
        top = Application.objects.filter(gig=gig).first()
        Application.objects.filter(pk=top.pk).update(fit_score=90)
        transition(top.pk, "shortlisted", actor="vendor", user=gig.vendor)
        vendor = client_for(gig.vendor)
        url = f"/api/v1/gigs/{gig.pk}/applications/"
        results = vendor.get(url).json()["results"]
        assert [r["fit"]["score"] for r in results] == [90, 40, 40]
        assert results[0]["attachment_count"] == 1
        assert [r["id"] for r in vendor.get(url, {"status": "shortlisted"}).json()["results"]] == [
            str(top.pk)
        ]
        assert len(vendor.get(url, {"min_score": 50}).json()["results"]) == 1
        assert len(vendor.get(url, {"sort": "oldest"}).json()["results"]) == 3
        assert vendor.get(url, {"sort": "random"}).status_code == 400

    def test_list_query_count_does_not_grow(self):
        def queries(gig) -> int:
            with CaptureQueriesContext(connection) as ctx:
                response = client_for(gig.vendor).get(f"/api/v1/gigs/{gig.pk}/applications/")
            assert response.status_code == 200
            return len(ctx.captured_queries)

        assert queries(self.setup_applicants(2)) == queries(self.setup_applicants(6))

    def test_detail_has_signed_urls_and_badges_but_no_contact_details(self):
        gig = self.setup_applicants(1)
        application = Application.objects.get(gig=gig)
        profile = application.talent.talent_profile
        response = client_for(gig.vendor).get(f"/api/v1/applications/{application.pk}/")
        assert response.status_code == 200
        data = response.json()
        assert data["attachments"][0]["url"].startswith("https://")
        assert data["applicant"]["badges"] == ["id_verified"]
        text = json.dumps(data)
        for secret in (
            application.talent.phone,
            profile.emergency_contact_phone,
            profile.emergency_contact_name,
            str(profile.date_of_birth),
        ):
            assert secret not in text
        assert "email" not in text and "instagram_handle" not in text

    def test_only_the_gigs_vendor(self):
        gig = self.setup_applicants(1)
        application = Application.objects.get(gig=gig)
        other = client_for(VendorFactory())
        assert other.get(f"/api/v1/gigs/{gig.pk}/applications/").status_code == 404
        assert other.get(f"/api/v1/applications/{application.pk}/").status_code == 404
        assert (
            client_for(eligible_talent()).get(f"/api/v1/gigs/{gig.pk}/applications/").status_code
            == 403
        )
        assert (
            client_for(AdminUserFactory())
            .get(f"/api/v1/applications/{application.pk}/")
            .status_code
            == 200
        )


class TestTalentViews:
    def test_mine_detail_and_withdraw(self):
        talent, gig = eligible_talent(), live_gig()
        application_id = apply_via_api(talent, gig).json()["id"]
        client = client_for(talent)
        assert [a["id"] for a in client.get("/api/v1/applications/mine/").json()["results"]] == [
            application_id
        ]
        assert client.get(f"/api/v1/applications/{application_id}/").status_code == 200

        response = client.post(
            f"/api/v1/applications/{application_id}/withdraw/", {"reason": "Exams"}, format="json"
        )
        assert response.status_code == 200
        assert (
            response.json()["status"] == "withdrawn" and response.json()["status_reason"] == "Exams"
        )
        again = client.post(f"/api/v1/applications/{application_id}/withdraw/", {}, format="json")
        assert again.status_code == 409

        stranger = client_for(eligible_talent())
        assert stranger.get(f"/api/v1/applications/{application_id}/").status_code == 404
        assert (
            stranger.post(
                f"/api/v1/applications/{application_id}/withdraw/", {}, format="json"
            ).status_code
            == 404
        )

    def test_reapply_after_withdrawing(self):
        talent, gig = eligible_talent(), live_gig()
        first = apply_via_api(talent, gig).json()["id"]
        client_for(talent).post(f"/api/v1/applications/{first}/withdraw/", {}, format="json")
        assert apply_via_api(talent, gig, proposed_start=str(in_days(33))).status_code == 201


def test_every_endpoint_is_in_the_openapi_schema(tmp_path):
    out = tmp_path / "schema.yaml"
    call_command("spectacular", "--file", str(out), "--validate", "--fail-on-warn")
    paths = set(yaml.safe_load(out.read_text())["paths"])
    assert {
        "/api/v1/gigs/{gig_id}/applications/",
        "/api/v1/applications/mine/",
        "/api/v1/applications/{application_id}/",
        "/api/v1/applications/{application_id}/withdraw/",
    } <= paths
