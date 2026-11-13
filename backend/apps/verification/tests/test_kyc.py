import time
from datetime import timedelta

import pytest

from apps.accounts.tests.factories import VendorFactory
from apps.common.models import AuditLog
from apps.verification.constants import BadgeKind, CaseStatus, DocumentStatus, DocumentType
from apps.verification.models import KycWebhookEvent, VerificationDocument
from apps.verification.providers.base import (
    InvalidWebhook,
    KycOutcome,
    KycProviderNotConfigured,
    KycResult,
    get_kyc_provider,
)
from apps.verification.providers.external import ExternalKycProvider
from apps.verification.providers.fake import FakeKycProvider
from apps.verification.services.cases import active_badge_kinds
from apps.verification.services.kyc import (
    WebhookOutcome,
    handle_webhook,
    start_id_check,
    sync_pending,
)

pytestmark = pytest.mark.django_db


def deliver(reference, outcome, *, key=None, **extra):
    body, headers = FakeKycProvider.webhook_request(
        KycResult(reference=reference, outcome=outcome, **extra), key=key
    )
    return handle_webhook(headers, body)


@pytest.fixture
def started():
    vendor = VendorFactory()
    case, session = start_id_check(vendor, document_type=DocumentType.AADHAAR)
    return vendor, case, session


def test_start_records_only_the_provider_reference(started):
    _vendor, case, session = started
    assert case.status == CaseStatus.SUBMITTED
    doc = VerificationDocument.objects.get(case=case)
    assert doc.provider == "fake" and doc.provider_reference == session.reference
    assert doc.media is None and doc.masked_value == ""
    assert session.client_token and session.redirect_url


def test_approval_by_webhook_grants_the_id_badge(started):
    vendor, case, session = started
    assert (
        deliver(session.reference, KycOutcome.APPROVED, id_last_four="9012")
        == WebhookOutcome.APPLIED
    )
    case.refresh_from_db()
    assert case.status == CaseStatus.APPROVED and case.reviewer is None
    assert case.details["id_last_four"] == "9012"
    doc = case.documents.get()
    assert doc.status == DocumentStatus.VERIFIED and doc.masked_value == "9012"
    assert BadgeKind.ID_VERIFIED in active_badge_kinds(vendor)
    assert AuditLog.objects.get(action="verification.case.approved").actor is None


def test_rejection_and_manual_review(started):
    _vendor, case, session = started
    assert deliver(session.reference, KycOutcome.MANUAL_REVIEW, reason="Glare on ID") == "applied"
    case.refresh_from_db()
    assert case.status == CaseStatus.IN_REVIEW
    deliver(session.reference, KycOutcome.REJECTED, reason="Face doesn't match.")
    case.refresh_from_db()
    assert case.status == CaseStatus.REJECTED and case.reason == "Face doesn't match."
    assert case.documents.get().status == DocumentStatus.FAILED


def test_repeated_idempotency_key_is_applied_once(started):
    _vendor, case, session = started
    assert deliver(session.reference, KycOutcome.APPROVED, key="evt-1") == WebhookOutcome.APPLIED
    assert deliver(session.reference, KycOutcome.REJECTED, key="evt-1") == WebhookOutcome.DUPLICATE
    case.refresh_from_db()
    assert case.status == CaseStatus.APPROVED
    assert KycWebhookEvent.objects.get().outcome == WebhookOutcome.APPLIED


def test_pending_unknown_and_stale_results_change_nothing(started):
    vendor, case, session = started
    assert deliver(session.reference, KycOutcome.PENDING) == WebhookOutcome.PENDING
    assert deliver("fake_nope", KycOutcome.APPROVED) == WebhookOutcome.UNKNOWN_REFERENCE
    # A newer check replaces the first; the first's result no longer counts.
    _, newer = start_id_check(vendor, document_type=DocumentType.PASSPORT)
    assert deliver(session.reference, KycOutcome.APPROVED) == WebhookOutcome.STALE
    case.refresh_from_db()
    assert case.status == CaseStatus.SUBMITTED
    assert deliver(newer.reference, KycOutcome.APPROVED) == WebhookOutcome.APPLIED


def test_results_after_a_decision_are_ignored(started):
    _vendor, _case, session = started
    deliver(session.reference, KycOutcome.APPROVED)
    assert deliver(session.reference, KycOutcome.REJECTED) == WebhookOutcome.IGNORED


def test_new_id_on_an_approved_case_goes_back_to_review(started):
    vendor, case, session = started
    deliver(session.reference, KycOutcome.APPROVED)
    case, newer = start_id_check(vendor, document_type=DocumentType.PASSPORT)
    assert case.status == CaseStatus.IN_REVIEW
    assert BadgeKind.ID_VERIFIED not in active_badge_kinds(vendor)
    deliver(newer.reference, KycOutcome.APPROVED)
    assert BadgeKind.ID_VERIFIED in active_badge_kinds(vendor)


def test_only_id_documents_can_start_a_check():
    with pytest.raises(ValueError):
        start_id_check(VendorFactory(), document_type=DocumentType.PAN)


def test_admin_cannot_start_an_id_check():
    from apps.accounts.tests.factories import AdminUserFactory
    from apps.verification.services.cases import CheckNotAvailable

    with pytest.raises(CheckNotAvailable):
        start_id_check(AdminUserFactory(), document_type=DocumentType.AADHAAR)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda b, h: (b + b" ", h),  # body changed after signing
        lambda b, h: (b, {**h, "X-Kyc-Signature": "0" * 64}),
        lambda b, h: (b, {k: v for k, v in h.items() if k != "Idempotency-Key"}),
        lambda b, h: (b, {**h, "X-Kyc-Timestamp": str(int(time.time()) - 3600)}),
    ],
    ids=["body", "signature", "no-key", "stale"],
)
def test_bad_webhooks_are_refused(started, tamper):
    _, _, session = started
    body, headers = FakeKycProvider.webhook_request(
        KycResult(reference=session.reference, outcome=KycOutcome.APPROVED)
    )
    body, headers = tamper(body, headers)
    with pytest.raises(InvalidWebhook):
        handle_webhook(headers, body)
    assert not KycWebhookEvent.objects.exists()


def test_webhook_needs_a_secret(settings, started):
    _, _, session = started
    body, headers = FakeKycProvider.webhook_request(
        KycResult(reference=session.reference, outcome=KycOutcome.APPROVED)
    )
    settings.KYC_WEBHOOK_SECRET = ""
    with pytest.raises(InvalidWebhook):
        handle_webhook(headers, body)


def test_sync_pending_polls_the_provider(started):
    _vendor, case, session = started
    provider = get_kyc_provider()
    provider.set_result(KycResult(reference=session.reference, outcome=KycOutcome.APPROVED))
    assert sync_pending(older_than=timedelta(hours=1)) == {}  # too recent
    assert sync_pending(older_than=timedelta(0)) == {WebhookOutcome.APPLIED: 1}
    case.refresh_from_db()
    assert case.status == CaseStatus.APPROVED


def test_external_stub_says_not_configured():
    stub = ExternalKycProvider()
    with pytest.raises(KycProviderNotConfigured):
        stub.start_check(case_id="c", user_id="u", document_type="aadhaar")
    with pytest.raises(KycProviderNotConfigured):
        stub.get_result("ref")
    with pytest.raises(KycProviderNotConfigured):
        stub.verify_webhook({}, b"{}")


def test_failed_start_leaves_no_trace(settings):
    settings.KYC_PROVIDER = "apps.verification.providers.external.ExternalKycProvider"
    vendor = VendorFactory()
    with pytest.raises(KycProviderNotConfigured):
        start_id_check(vendor, document_type=DocumentType.AADHAAR)
    assert not VerificationDocument.objects.exists()
    assert not AuditLog.objects.exists()


def test_restarting_after_rejection_is_allowed(started):
    vendor, case, session = started
    deliver(session.reference, KycOutcome.REJECTED)
    case, _ = start_id_check(vendor, document_type=DocumentType.VOTER_ID)
    assert case.status == CaseStatus.SUBMITTED
    assert case.documents.count() == 2
