from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.accounts.tests.factories import VendorFactory
from apps.verification.constants import CaseStatus, DocumentType
from apps.verification.services.kyc import start_id_check
from apps.verification.tests.factories import CaseFactory

pytestmark = pytest.mark.django_db


def run(*args) -> str:
    out = StringIO()
    call_command(*args, stdout=out)
    return out.getvalue()


def test_fake_kyc_result_finishes_a_local_check():
    case, session = start_id_check(VendorFactory(), document_type=DocumentType.AADHAAR)
    assert "applied" in run("fake_kyc_result", session.reference, "approved")
    case.refresh_from_db()
    assert case.status == CaseStatus.APPROVED


def test_fake_kyc_result_refuses_a_real_provider(settings):
    settings.KYC_PROVIDER = "apps.verification.providers.external.ExternalKycProvider"
    with pytest.raises(CommandError):
        run("fake_kyc_result", "ref", "approved")


def test_expire_and_sync_commands():
    CaseFactory(status=CaseStatus.APPROVED, expires_at=timezone.now())
    assert "Expired 1" in run("expire_verifications")
    assert "nothing pending" in run("sync_kyc_results")
