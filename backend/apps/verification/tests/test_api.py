from unittest import mock

import pytest
import yaml
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.profiles.tests.factories import TalentProfileFactory, VendorProfileFactory
from apps.verification.constants import CaseStatus, CheckType
from apps.verification.models import VerificationCase
from apps.verification.providers.base import KycOutcome, KycResult
from apps.verification.providers.fake import FakeKycProvider
from apps.verification.tests.factories import (
    CaseFactory,
    MediaFileFactory,
    client_for,
)

pytestmark = pytest.mark.django_db

BASE = "/api/v1/verification"


def start_id(user, document_type="aadhaar"):
    return client_for(user).post(
        f"{BASE}/checks/id/", {"document_type": document_type}, format="json"
    )


def post_webhook(result, key="evt-1"):
    body, headers = FakeKycProvider.webhook_request(result, key=key)
    extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    return APIClient().post(
        f"{BASE}/webhooks/kyc/", data=body, content_type="application/json", **extra
    )


class TestMe:
    def test_vendor_sees_their_three_checks(self):
        vendor = VendorFactory()
        body = client_for(vendor).get(f"{BASE}/me/").json()
        assert [c["check_type"] for c in body["checks"]] == [
            CheckType.ID_SELFIE,
            CheckType.BUSINESS,
            CheckType.PROPERTY,
        ]
        assert all(c["cases"] == [] and c["required"] for c in body["checks"])
        assert body["badges"] == [] and body["trusted_member"] is False

    def test_talent_certificates_are_optional(self):
        body = client_for(TalentFactory()).get(f"{BASE}/me/").json()
        required = {c["check_type"]: c["required"] for c in body["checks"]}
        assert required == {
            "id_selfie": True,
            "social_account": True,
            "certificate": False,
            "reference": True,
        }

    def test_needs_sign_in(self):
        assert APIClient().get(f"{BASE}/me/").status_code == 401


class TestIdCheck:
    def test_start_then_webhook_approves(self):
        vendor = VendorFactory()
        response = start_id(vendor)
        assert response.status_code == 201
        body = response.json()
        assert body["case"]["status"] == CaseStatus.SUBMITTED
        reference = body["session"]["reference"]
        assert body["case"]["documents"][0]["masked_value"] == ""

        hook = post_webhook(
            KycResult(reference=reference, outcome=KycOutcome.APPROVED, id_last_four="4321")
        )
        assert hook.status_code == 200 and hook.json() == {"outcome": "applied"}
        again = post_webhook(KycResult(reference=reference, outcome=KycOutcome.APPROVED))
        assert again.json() == {"outcome": "duplicate"}

        me = client_for(vendor).get(f"{BASE}/me/").json()
        assert [b["kind"] for b in me["badges"]] == ["id_verified"]
        [id_case] = me["checks"][0]["cases"]
        assert id_case["status"] == CaseStatus.APPROVED
        assert id_case["documents"][0]["masked_value"] == "4321"
        assert "provider_reference" not in id_case["documents"][0]

    def test_bad_signature_is_401(self):
        body, headers = FakeKycProvider.webhook_request(
            KycResult(reference="x", outcome=KycOutcome.APPROVED)
        )
        headers["X-Kyc-Signature"] = "0" * 64
        extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
        response = APIClient().post(
            f"{BASE}/webhooks/kyc/", data=body, content_type="application/json", **extra
        )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_webhook"

    def test_no_provider_configured_is_503(self, settings):
        settings.KYC_PROVIDER = "apps.verification.providers.external.ExternalKycProvider"
        response = start_id(VendorFactory())
        assert response.status_code == 503
        assert response.json()["code"] == "kyc_unavailable"
        hook = APIClient().post(
            f"{BASE}/webhooks/kyc/", data=b"{}", content_type="application/json"
        )
        assert hook.status_code == 503

    def test_rejects_non_id_documents_and_users_without_a_role(self):
        assert start_id(VendorFactory(), document_type="pan").status_code == 400
        assert start_id(AdminUserFactory()).status_code == 403

    def test_starts_are_rate_limited(self):
        from apps.verification.throttles import KycStartThrottle

        vendor = VendorFactory()
        with mock.patch.object(KycStartThrottle, "rate", "1/day", create=True):
            assert start_id(vendor).status_code == 201
            assert start_id(vendor).status_code == 429


class TestVendorChecks:
    def test_business(self):
        vendor = VendorProfileFactory().user
        response = client_for(vendor).post(
            f"{BASE}/checks/business/",
            {"pan": "ABCPE1234F", "gstin": "27ABCPE1234F1Z5"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["details"]["pan_last_four"] == "234F"
        bad = client_for(vendor).post(f"{BASE}/checks/business/", {"pan": "nope"}, format="json")
        assert bad.status_code == 400

    def test_talent_cannot_use_vendor_checks(self):
        response = client_for(TalentFactory()).post(
            f"{BASE}/checks/business/", {"pan": "ABCPE1234F"}, format="json"
        )
        assert response.status_code == 403


class TestTalentChecks:
    def test_social_certificates_reference(self):
        talent = TalentProfileFactory(instagram_handle="painter").user
        client = client_for(talent)
        social = client.post(f"{BASE}/checks/social/")
        assert social.status_code == 200
        assert social.json()["details"]["bio_code"].startswith("BARTERLY-")

        doc = MediaFileFactory(owner=talent, kind="document", content_type="application/pdf")
        certs = client.post(
            f"{BASE}/checks/certificates/",
            {"certificates": [{"media_id": str(doc.pk), "title": "Barista course"}]},
            format="json",
        )
        assert certs.status_code == 200
        empty = client.post(f"{BASE}/checks/certificates/", {"certificates": []}, format="json")
        assert empty.status_code == 400

        ref = client.post(
            f"{BASE}/checks/reference/",
            {"name": "Asha", "phone": "9811122233", "relationship": "Former manager"},
            format="json",
        )
        assert ref.status_code == 200
        again = client.post(
            f"{BASE}/checks/reference/",
            {"name": "Asha", "phone": "9811122233", "relationship": "Former manager"},
            format="json",
        )
        assert again.status_code == 200  # still waiting, so it can be corrected

    def test_vendor_cannot_use_talent_checks(self):
        assert client_for(VendorFactory()).post(f"{BASE}/checks/social/").status_code == 403


class TestReview:
    def test_queue_detail_and_decisions(self):
        admin = AdminUserFactory()
        oldest = CaseFactory(check_type=CheckType.BUSINESS)
        CaseFactory(check_type=CheckType.REFERENCE, status=CaseStatus.APPROVED)
        client = client_for(admin)

        queue = client.get(f"{BASE}/admin/cases/", {"status": "submitted"}).json()
        assert [c["id"] for c in queue["results"]] == [str(oldest.pk)]
        assert queue["results"][0]["user_phone"] == oldest.user.phone

        detail = client.get(f"{BASE}/admin/cases/{oldest.pk}/")
        assert detail.status_code == 200

        no_reason = client.post(
            f"{BASE}/admin/cases/{oldest.pk}/decision/", {"decision": "reject"}, format="json"
        )
        assert no_reason.status_code == 400
        approved = client.post(
            f"{BASE}/admin/cases/{oldest.pk}/decision/", {"decision": "approve"}, format="json"
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == CaseStatus.APPROVED
        assert approved.json()["reviewer_id"] == str(admin.pk)

        twice = client.post(
            f"{BASE}/admin/cases/{oldest.pk}/decision/", {"decision": "approve"}, format="json"
        )
        assert twice.status_code == 409
        missing = client.post(
            f"{BASE}/admin/cases/00000000-0000-0000-0000-000000000000/decision/",
            {"decision": "approve"},
            format="json",
        )
        assert missing.status_code == 404

    def test_bad_user_filter_is_400(self):
        response = client_for(AdminUserFactory()).get(f"{BASE}/admin/cases/", {"user": "nope"})
        assert response.status_code == 400

    def test_only_admins(self):
        case = CaseFactory()
        assert client_for(case.user).get(f"{BASE}/admin/cases/").status_code == 403
        response = client_for(case.user).post(
            f"{BASE}/admin/cases/{case.pk}/decision/", {"decision": "approve"}, format="json"
        )
        assert response.status_code == 403
        assert VerificationCase.objects.get(pk=case.pk).status == CaseStatus.SUBMITTED


def test_every_endpoint_is_in_the_openapi_schema(tmp_path):
    out = tmp_path / "schema.yaml"
    call_command("spectacular", "--file", str(out), "--validate", "--fail-on-warn")
    paths = yaml.safe_load(out.read_text())["paths"]
    ours = {p for p in paths if p.startswith("/api/v1/verification/")}
    assert ours == {
        "/api/v1/verification/me/",
        "/api/v1/verification/checks/id/",
        "/api/v1/verification/checks/business/",
        "/api/v1/verification/checks/social/",
        "/api/v1/verification/checks/certificates/",
        "/api/v1/verification/checks/reference/",
        "/api/v1/verification/webhooks/kyc/",
        "/api/v1/verification/admin/cases/",
        "/api/v1/verification/admin/cases/{case_id}/",
        "/api/v1/verification/admin/cases/{case_id}/decision/",
    }
