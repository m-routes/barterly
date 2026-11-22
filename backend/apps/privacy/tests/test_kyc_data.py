"""KYC stays with the provider: we keep the outcome and the last four, nothing more."""

import pytest
from django.db import IntegrityError

from apps.verification.models import KycWebhookEvent, VerificationDocument
from apps.verification.services.kyc import masked_last_four, safe_reason


def test_we_keep_four_characters_of_an_id_at_most():
    assert VerificationDocument._meta.get_field("masked_value").max_length == 4
    assert masked_last_four("1234 5678 9012") == "9012"
    assert masked_last_four("ABCPD1234E") == "234E"
    assert masked_last_four("xx-12") == "XX12"
    assert masked_last_four("") == ""


def test_a_provider_reason_never_carries_an_id_number():
    assert safe_reason("Aadhaar 1234 5678 9012 didn't match") == (
        "Aadhaar [number removed] didn't match"
    )
    assert safe_reason("PAN ABCPD1234E is invalid") == "PAN [number removed] is invalid"
    assert safe_reason("Selfie too dark") == "Selfie too dark"


def test_webhooks_store_no_payload():
    fields = {f.name for f in KycWebhookEvent._meta.fields}
    assert not fields & {"payload", "body", "raw"}


@pytest.mark.django_db
def test_id_documents_cannot_be_uploaded():
    from apps.verification.tests.factories import CaseFactory, MediaFileFactory

    case = CaseFactory()
    with pytest.raises(IntegrityError):
        VerificationDocument.objects.create(
            case=case, document_type="aadhaar", media=MediaFileFactory(owner=case.user)
        )
