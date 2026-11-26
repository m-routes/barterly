"""Drawing up, signing and changing agreements.

- draw_up(): when an offer is accepted, version 1 is made from its terms.
- render(): the version's PDF is drawn up, stored in Cloud Storage and its SHA-256
  recorded. It runs after the booking's transaction commits (render_quietly) and the
  render_agreements job retries any left over, so a slow PDF never blocks a booking.
- sign(): one side signs one version through the e-sign provider. When both have signed,
  the version is in force and the one before is superseded. Version 1 in force confirms
  the booking (apps.bookings.confirmation.confirm_signed), in the same transaction.
- propose_change(): either side changes the terms as a new version that both must sign;
  the version in force stays in force until then. decline_change() turns it down.

Locks: gig, then booking, then agreement, then version (the same order as bookings).
Every status change is audited and published as agreement.<event>.
"""

import hashlib
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.agreements import pdf
from apps.agreements.esign.base import (
    Challenge,
    ProviderUnavailable,
    SigningAttempt,
    SigningRefused,
    get_provider,
)
from apps.agreements.models import Agreement, AgreementVersion, Signature, VersionStatus
from apps.bookings import confirmation
from apps.bookings.lifecycle import BEFORE_CHECK_IN, HOLDS_DATES, BookingStatus
from apps.bookings.models import Booking
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import client_ip, log_action, snapshot
from apps.gigs.models import Gig
from apps.media.storage import get_storage
from apps.offers import terms as offer_terms
from apps.offers.models import Party

logger = logging.getLogger(__name__)

# The booking states in which an agreement can be signed or changed.
OPEN_BOOKING = frozenset(
    {
        BookingStatus.SIGNING,
        BookingStatus.CONFIRMED,
        BookingStatus.CHECKED_IN,
        BookingStatus.DELIVERING,
    }
)
# Every term but how the gig is paid can change by a new version.
CHANGEABLE = (
    "start_date",
    "end_date",
    "hours_per_day",
    "days_per_week",
    "stay_type",
    "meals",
    "stipend_amount",
    "stipend_period",
    "deliverables",
    "usage_rights",
    "cancellation_policy",
)
AUDIT_FIELDS = ["status", "status_reason"]


class AgreementError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def party_of(user, booking: Booking) -> str | None:
    if booking.talent_id == user.pk:
        return Party.TALENT
    if booking.vendor_id == user.pk:
        return Party.VENDOR
    return None


def _payload(version: AgreementVersion, booking: Booking, **extra) -> dict:
    return {
        "agreement_id": str(version.agreement_id),
        "version_id": str(version.pk),
        "version": version.number,
        "booking_id": str(booking.pk),
        "gig_title": booking.gig.title,
        "talent_id": str(booking.talent_id),
        "vendor_id": str(booking.vendor_id),
        **extra,
    }


def _new_version(agreement, *, number, terms, now, offer=None, proposed_by=None, reason="",
                 changed=()) -> AgreementVersion:  # fmt: skip
    return AgreementVersion.objects.create(
        agreement=agreement,
        number=number,
        terms=terms,
        terms_sha256=offer_terms.digest(terms),
        offer=offer,
        proposed_by=proposed_by,
        change_reason=reason,
        changed_fields=list(changed),
        template=pdf.CURRENT_TEMPLATE,
        template_sha256=pdf.template_sha256(pdf.CURRENT_TEMPLATE),
        created_at=now,
    )


def _set_status(version, status, *, user, reason="", now, request=None, action=None) -> None:
    before = snapshot(version, AUDIT_FIELDS)
    version.status = status
    version.status_reason = reason
    fields = ["status", "status_reason"]
    if status == VersionStatus.ACTIVE:
        version.in_force_at = now
        fields.append("in_force_at")
    version.save(update_fields=fields)
    log_action(
        actor=user,
        action=action or f"agreement.version_{status}",
        obj=version,
        before=before,
        after={**snapshot(version, AUDIT_FIELDS), "number": version.number},
        request=request,
    )


# ---------- Drawing up ----------


def draw_up(booking: Booking, offer, *, user, request=None, now=None) -> AgreementVersion:
    """Version 1, from the accepted offer. Called inside the booking's transaction."""
    now = now or timezone.now()
    agreement = Agreement.objects.create(booking=booking, created_at=now)
    version = _new_version(agreement, number=1, terms=offer.terms, offer=offer, now=now)
    log_action(
        actor=user,
        action="agreement.drawn_up",
        obj=version,
        after={"number": 1, "terms_sha256": version.terms_sha256, "offer_id": str(offer.pk)},
        request=request,
    )
    publish(DomainEvent("agreement.ready", _payload(version, booking), occurred_at=now))
    return version


def storage_key(version: AgreementVersion, sha256: str) -> str:
    return f"agreements/{version.agreement_id}/v{version.number}-{sha256[:16]}.pdf"


def render(version_id) -> AgreementVersion:
    """Draw up and store the version's PDF. Idempotent: a rendered version is left alone."""
    version = AgreementVersion.objects.select_related(
        "agreement__booking__gig__property",
        "agreement__booking__vendor",
        "agreement__booking__talent",
    ).get(pk=version_id)
    if version.rendered:
        return version
    data = pdf.render_pdf(version)
    sha256 = hashlib.sha256(data).hexdigest()
    key = storage_key(version, sha256)
    get_storage().write(key, data, content_type="application/pdf")
    with transaction.atomic():
        locked = AgreementVersion.objects.select_for_update().get(pk=version_id)
        if locked.rendered:  # someone else got there first; their file stands
            return locked
        locked.pdf_key, locked.pdf_sha256, locked.pdf_size = key, sha256, len(data)
        locked.rendered_at = timezone.now()
        locked.save(update_fields=["pdf_key", "pdf_sha256", "pdf_size", "rendered_at"])
        log_action(
            actor=None,
            action="agreement.rendered",
            obj=locked,
            after={"pdf_sha256": sha256, "pdf_size": len(data), "template": locked.template},
        )
    return locked


def render_quietly(version_id) -> AgreementVersion | None:
    try:
        return render(version_id)
    except Exception:
        logger.exception(
            "Agreement render failed; the job will retry", extra={"id": str(version_id)}
        )
        return None


def render_pending(now=None) -> dict[str, int]:
    """Job: render versions waiting for signatures that have no PDF yet."""
    pending = AgreementVersion.objects.filter(
        status=VersionStatus.AWAITING, pdf_sha256=""
    ).values_list("pk", flat=True)
    done = failed = 0
    for pk in list(pending[:100]):
        if render_quietly(pk):
            done += 1
        else:
            failed += 1
    return {"rendered": done, "failed": failed}


# ---------- Signing ----------


def _signable(version: AgreementVersion, user) -> str:
    booking = version.agreement.booking
    party = party_of(user, booking)
    if party is None:
        raise AgreementVersion.DoesNotExist
    if version.status != VersionStatus.AWAITING:
        raise AgreementError(f"Version {version.number} is {version.get_status_display().lower()}.")
    if booking.status not in OPEN_BOOKING:
        raise AgreementError(f"The booking is {booking.get_status_display().lower()}.")
    if not version.rendered:
        raise AgreementError("The document is still being prepared. Try again in a moment.", 503)
    if version.signatures.filter(party=party).exists():
        raise AgreementError("You've already signed this version.")
    return party


def _load(version_id) -> AgreementVersion:
    return AgreementVersion.objects.select_related(
        "agreement__booking__gig", "agreement__current_version"
    ).get(pk=version_id)


def challenge(version_id, *, user) -> Challenge:
    version = _load(version_id)
    _signable(version, user)
    return get_provider().challenge(version=version, signer=user)


def sign(version_id, *, user, consent: bool, document_sha256: str, otp_token: str = "",
         request=None, now=None) -> AgreementVersion:  # fmt: skip
    """Sign one version. The provider checks consent (and the OTP) before anything is
    locked; the checks are repeated under the locks before the signature is stored."""
    now = now or timezone.now()
    version = _load(version_id)
    party = _signable(version, user)
    if document_sha256 != version.pdf_sha256:
        raise AgreementError(
            "This isn't the document on file. Reload it and read it again before signing.", 400
        )
    headers = getattr(request, "headers", {}) if request else {}
    attempt = SigningAttempt(
        version=version,
        signer=user,
        party=party,
        consent=consent,
        otp_token=otp_token,
        ip=client_ip(request),
        user_agent=(headers.get("User-Agent") or "")[:300],
        device=(headers.get("X-Client-Device") or "")[:120],
        now=now,
    )
    provider = get_provider()
    try:
        evidence = provider.sign(attempt)
    except SigningRefused as exc:
        raise AgreementError(str(exc), 400) from exc
    except ProviderUnavailable as exc:
        raise AgreementError("We can't confirm signatures right now. Try again soon.", 503) from exc

    booking_id = version.agreement.booking_id
    with transaction.atomic():
        gig_id = Booking.objects.values_list("gig_id", flat=True).get(pk=booking_id)
        Gig.objects.select_for_update().get(pk=gig_id)
        booking = Booking.objects.select_for_update().select_related("gig").get(pk=booking_id)
        agreement = Agreement.objects.select_for_update().get(pk=version.agreement_id)
        version = AgreementVersion.objects.select_for_update().get(pk=version_id)
        version.agreement = agreement
        agreement.booking = booking
        _signable(version, user)
        signature = Signature.objects.create(
            version=version,
            party=party,
            user=user,
            provider=evidence.provider,
            provider_reference=evidence.reference,
            document_sha256=document_sha256,
            consent_text=provider.challenge(version=version, signer=user).consent_text,
            phone=evidence.phone,
            otp_verified_at=evidence.otp_verified_at,
            ip=attempt.ip,
            user_agent=attempt.user_agent,
            device=attempt.device,
            evidence=evidence.extra,
            signed_at=now,
        )
        log_action(
            actor=user,
            action="agreement.signed",
            obj=version,
            after={
                "party": party,
                "number": version.number,
                "provider": signature.provider,
                "document_sha256": document_sha256,
                "signature_id": str(signature.pk),
            },
            request=request,
        )
        publish(
            DomainEvent("agreement.signed", _payload(version, booking, by=party), occurred_at=now)
        )
        if version.signatures.count() == len(Party.values):
            _put_in_force(agreement, version, booking, user=user, request=request, now=now)
            try:
                confirmation.confirm_signed(booking, version_number=version.number, now=now)
            except confirmation.ConfirmationRefused as exc:
                raise AgreementError(str(exc)) from exc
    return version


def _put_in_force(agreement, version, booking, *, user, request, now) -> None:
    start = date.fromisoformat(version.terms["start_date"])
    end = date.fromisoformat(version.terms["end_date"])
    dates_change = (start, end) != (booking.start_date, booking.end_date)
    if dates_change:
        if booking.status not in BEFORE_CHECK_IN:
            raise AgreementError(
                "The stay has started, so its dates can't change. Decline this version and "
                "propose one that keeps the dates."
            )
        clash = Booking.objects.filter(
            talent_id=booking.talent_id,
            status__in=HOLDS_DATES,
            start_date__lt=end,
            end_date__gt=start,
        ).exclude(pk=booking.pk)
        if clash.exists():
            raise AgreementError("The talent already has a booking for some of the new dates.")
    previous = agreement.current_version
    if previous is not None:
        _set_status(
            previous,
            VersionStatus.SUPERSEDED,
            user=user,
            reason=f"Replaced by version {version.number}.",
            now=now,
            request=request,
        )
    _set_status(version, VersionStatus.ACTIVE, user=user, now=now, request=request,
                action="agreement.in_force")  # fmt: skip
    agreement.current_version = version
    agreement.save(update_fields=["current_version"])
    if dates_change:
        before = snapshot(booking, ["start_date", "end_date"])
        booking.start_date, booking.end_date = start, end
        booking.save(update_fields=["start_date", "end_date", "updated_at"])
        log_action(
            actor=user,
            action="booking.dates_changed",
            obj=booking,
            before=before,
            after={
                **snapshot(booking, ["start_date", "end_date"]),
                "agreement_version": version.number,
            },
            request=request,
        )
    publish(DomainEvent("agreement.in_force", _payload(version, booking), occurred_at=now))


# ---------- Changing ----------


def propose_change(booking_id, *, user, changes: dict, reason: str, request=None, now=None):
    """Change the terms: a new version both must sign. Replaces any version still
    waiting for signatures; the version in force stays in force until then."""
    now = now or timezone.now()
    reason = reason.strip()
    if not reason:
        raise AgreementError("Say why the terms should change.", 400)
    unknown = sorted(set(changes) - set(CHANGEABLE))
    if unknown:
        raise AgreementError(f"These can't be changed: {', '.join(unknown)}.", 400)
    with transaction.atomic():
        gig_id = Booking.objects.values_list("gig_id", flat=True).get(pk=booking_id)
        Gig.objects.select_for_update().get(pk=gig_id)
        booking = Booking.objects.select_for_update().select_related("gig").get(pk=booking_id)
        party = party_of(user, booking)
        if party is None:
            raise Booking.DoesNotExist
        agreement = Agreement.objects.select_for_update().filter(booking=booking).first()
        if agreement is None:
            raise AgreementError("This booking has no agreement.")
        if booking.status not in OPEN_BOOKING:
            raise AgreementError(f"The booking is {booking.get_status_display().lower()}.")
        waiting = (
            agreement.versions.select_for_update().filter(status=VersionStatus.AWAITING).first()
        )
        base = agreement.current_version or waiting
        merged = {**base.terms, **changes}
        dates_change = any(merged[f] != base.terms[f] for f in offer_terms.DATE_FIELDS)
        if dates_change and booking.status not in BEFORE_CHECK_IN:
            raise AgreementError("The stay has started, so its dates can't change.")
        terms = offer_terms.validate(
            merged,
            compensation_model=base.terms["compensation_model"],
            today=timezone.localdate(now) if dates_change else date.min,
        )
        changed = offer_terms.changed_fields(base.terms, terms)
        if not changed:
            raise AgreementError("Change at least one of the terms.", 400)
        number = (agreement.versions.aggregate(n=Max("number"))["n"] or 0) + 1
        if waiting is not None:
            _set_status(
                waiting,
                VersionStatus.VOIDED,
                user=user,
                reason=f"Replaced by version {number} before it was signed.",
                now=now,
                request=request,
            )
        version = _new_version(
            agreement, number=number, terms=terms, now=now, proposed_by=user, reason=reason,
            changed=changed,
        )  # fmt: skip
        log_action(
            actor=user,
            action="agreement.change_proposed",
            obj=version,
            before={f: base.terms[f] for f in changed},
            after={**{f: terms[f] for f in changed}, "number": number, "reason": reason},
            request=request,
        )
        publish(
            DomainEvent(
                "agreement.change_proposed",
                _payload(version, booking, by=party, changed=changed, reason=reason),
                occurred_at=now,
            )
        )
    return render_quietly(version.pk) or version


def decline_change(version_id, *, user, reason: str = "", request=None, now=None):
    """Turn down (or, for its proposer, withdraw) a change waiting for signatures."""
    now = now or timezone.now()
    with transaction.atomic():
        version = (
            AgreementVersion.objects.select_for_update()
            .select_related("agreement__booking__gig")
            .get(pk=version_id)
        )
        booking = version.agreement.booking
        party = party_of(user, booking)
        if party is None:
            raise AgreementVersion.DoesNotExist
        if version.status != VersionStatus.AWAITING:
            raise AgreementError(
                f"Version {version.number} is {version.get_status_display().lower()}."
            )
        if version.agreement.current_version_id is None:
            raise AgreementError(
                "The first version can't be declined. If the stay isn't going ahead, "
                "cancel the booking."
            )
        _set_status(
            version,
            VersionStatus.DECLINED,
            user=user,
            reason=reason.strip(),
            now=now,
            request=request,
            action="agreement.change_declined",
        )
        publish(
            DomainEvent(
                "agreement.change_declined",
                _payload(version, booking, by=party, reason=reason.strip()),
                occurred_at=now,
            )
        )
    return version


def signed_url(version: AgreementVersion) -> str:
    """A short-lived link to the version's PDF (only ever handed to its parties)."""
    if not version.rendered:
        raise AgreementError("The document is still being prepared. Try again in a moment.", 503)
    return get_storage().signed_read_url(
        version.pdf_key,
        expires=timedelta(minutes=10),
        download_name=f"barterly-agreement-v{version.number}.pdf",
    )
