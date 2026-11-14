"""ID + selfie through the KYC provider: start a check, take its result.

Results arrive by signed webhook (handle_webhook). sync_pending() asks the provider
directly for checks whose webhook never came.
"""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.verification.constants import (
    ID_DOCUMENT_TYPES,
    RESUBMITTABLE,
    CaseStatus,
    CheckType,
    DocumentStatus,
)
from apps.verification.models import KycWebhookEvent, VerificationCase, VerificationDocument
from apps.verification.providers.base import KycOutcome, KycResult, KycSession, get_kyc_provider
from apps.verification.services.cases import InvalidTransition, locked_case, transition

logger = logging.getLogger(__name__)


class WebhookOutcome:
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    PENDING = "pending"
    STALE = "stale"
    IGNORED = "ignored"
    UNKNOWN_REFERENCE = "unknown_reference"


def start_id_check(
    user, *, document_type: str, request=None
) -> tuple[VerificationCase, KycSession]:
    """Open a provider session for an ID plus selfie.

    Starting again on an approved case (a new or changed ID) sends it back to review and
    takes the ID badge away until the provider approves the new one.
    """
    if document_type not in ID_DOCUMENT_TYPES:
        raise ValueError(f"{document_type} isn't an ID document.")
    provider = get_kyc_provider()
    with transaction.atomic():
        case = locked_case(user, CheckType.ID_SELFIE)
        if case.status in RESUBMITTABLE:
            target = CaseStatus.SUBMITTED
        elif case.status in (CaseStatus.APPROVED, CaseStatus.IN_REVIEW):
            target = CaseStatus.IN_REVIEW
        else:
            raise InvalidTransition(f"A {case.status} ID check can't be restarted.")
        # The provider has an HTTP timeout; holding the row lock for it is acceptable at
        # this volume and stops two sessions racing for one case.
        session = provider.start_check(
            case_id=str(case.pk), user_id=str(user.pk), document_type=document_type
        )
        case.subject_id = str(user.pk)
        VerificationDocument.objects.create(
            case=case,
            document_type=document_type,
            provider=provider.name,
            provider_reference=session.reference,
        )
        reason = "New ID submitted; re-checking." if target == CaseStatus.IN_REVIEW else ""
        transition(case, target, actor=user, reason=reason, request=request)
    return case, session


def handle_webhook(headers, body: bytes) -> str:
    """Verify, de-duplicate and apply one delivery. Raises InvalidWebhook for bad ones."""
    provider = get_kyc_provider()
    event = provider.verify_webhook(headers, body)
    with transaction.atomic():
        try:
            with transaction.atomic():
                record = KycWebhookEvent.objects.create(
                    provider=provider.name,
                    idempotency_key=event.idempotency_key,
                    provider_reference=event.result.reference,
                    outcome="received",
                )
        except IntegrityError:
            return WebhookOutcome.DUPLICATE
        outcome = apply_result(provider.name, event.result)
        record.outcome = outcome
        record.save(update_fields=["outcome"])
    return outcome


def apply_result(provider_name: str, result: KycResult) -> str:
    """Move the case to match the provider's outcome. Call inside a transaction."""
    doc = (
        VerificationDocument.objects.select_related("case")
        .filter(provider=provider_name, provider_reference=result.reference)
        .first()
    )
    if doc is None:
        logger.warning("KYC result for an unknown reference", extra={"reference": result.reference})
        return WebhookOutcome.UNKNOWN_REFERENCE
    case = VerificationCase.objects.select_for_update().select_related("user").get(pk=doc.case_id)
    latest = (
        case.documents.filter(document_type__in=ID_DOCUMENT_TYPES).order_by("-created_at").first()
    )
    if latest is None or latest.pk != doc.pk:
        # The user started a newer check; this one no longer decides anything.
        return WebhookOutcome.STALE
    if result.outcome == KycOutcome.PENDING:
        return WebhookOutcome.PENDING
    if case.status not in (CaseStatus.SUBMITTED, CaseStatus.IN_REVIEW):
        return WebhookOutcome.IGNORED

    if result.id_last_four:
        doc.masked_value = result.id_last_four[-4:]
        case.details = {**case.details, "id_last_four": doc.masked_value}
    if result.outcome == KycOutcome.MANUAL_REVIEW:
        doc.save(update_fields=["masked_value", "updated_at"])
        if case.status == CaseStatus.SUBMITTED:
            transition(case, CaseStatus.IN_REVIEW, actor=None, reason=result.reason)
        else:
            case.save(update_fields=["details", "updated_at"])
        return WebhookOutcome.APPLIED

    approved = result.outcome == KycOutcome.APPROVED
    doc.status = DocumentStatus.VERIFIED if approved else DocumentStatus.FAILED
    doc.save(update_fields=["status", "masked_value", "updated_at"])
    if approved:
        transition(case, CaseStatus.APPROVED, actor=None, reason="ID and selfie matched.")
    else:
        transition(
            case,
            CaseStatus.REJECTED,
            actor=None,
            reason=result.reason or "We couldn't verify your ID. Try again with a clear photo.",
        )
    return WebhookOutcome.APPLIED


def sync_pending(older_than: timedelta = timedelta(minutes=30)) -> dict[str, int]:
    """Poll the provider for ID checks with no result after `older_than`."""
    provider = get_kyc_provider()
    cutoff = timezone.now() - older_than
    docs = VerificationDocument.objects.filter(
        provider=provider.name,
        status=DocumentStatus.PENDING,
        document_type__in=ID_DOCUMENT_TYPES,
        created_at__lte=cutoff,
        case__status__in=[CaseStatus.SUBMITTED, CaseStatus.IN_REVIEW],
    ).values_list("provider_reference", flat=True)
    counts: dict[str, int] = {}
    for reference in docs:
        result = provider.get_result(reference)
        with transaction.atomic():
            outcome = apply_result(provider.name, result)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts
