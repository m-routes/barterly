"""Submitting the checks a reviewer decides on (everything except ID + selfie).

Each submit validates what it can automatically (formats, ownership, distances), records
the evidence, and moves the case to `submitted` for the trust team.
"""

import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.services.phone import normalize_phone
from apps.media.models import MediaFile, MediaStatus
from apps.media.policy import Kind
from apps.verification.constants import (
    RESUBMITTABLE,
    CaseStatus,
    CheckType,
    DocumentStatus,
    DocumentType,
)
from apps.verification.models import VerificationCase, VerificationDocument
from apps.verification.services.cases import InvalidTransition, locked_case, transition
from apps.verification.validators import (
    distance_m,
    gstin_matches_pan,
    last_four,
    normalize_gstin,
    normalize_pan,
    validate_in_india,
)

UNUSABLE_MEDIA = (MediaStatus.REJECTED, MediaStatus.QUARANTINED, MediaStatus.PENDING_UPLOAD)


@dataclass(frozen=True)
class Certificate:
    media_id: str
    title: str


def _open_for_submission(user, check_type: str, *, prop=None) -> VerificationCase:
    case = locked_case(user, check_type, prop=prop)
    if case.status not in RESUBMITTABLE:
        raise InvalidTransition(
            f"This check is {case.get_status_display().lower()}; it can't be resubmitted now."
        )
    return case


def _submit(case: VerificationCase, *, user, request) -> VerificationCase:
    return transition(case, CaseStatus.SUBMITTED, actor=user, request=request)


def _own_media(user, ids: list[str], kind: str) -> dict[str, MediaFile]:
    found = {
        str(m.pk): m
        for m in MediaFile.objects.filter(pk__in=ids, owner=user, kind=kind).exclude(
            status__in=UNUSABLE_MEDIA
        )
    }
    missing = [i for i in ids if str(i) not in found]
    if missing:
        raise ValidationError(
            {"media_id": [f"No usable {kind} upload with id {', '.join(map(str, missing))}."]}
        )
    return found


def submit_business(user, *, pan: str, gstin: str = "", request=None) -> VerificationCase:
    """PAN (required) and GSTIN (optional; defaults to the profile's). Formats only."""
    pan = normalize_pan(pan)
    profile = getattr(user, "vendor_profile", None)
    if profile is not None and profile.is_deleted:
        profile = None
    gstin = gstin or (profile.gstin if profile else "")
    if gstin:
        gstin = normalize_gstin(gstin)
        if not gstin_matches_pan(gstin, pan):
            raise ValidationError({"gstin": ["This GSTIN belongs to a different PAN."]})
    with transaction.atomic():
        case = _open_for_submission(user, CheckType.BUSINESS)
        case.details = {
            "pan_last_four": last_four(pan),
            "gstin_last_four": last_four(gstin),
            "business_name": profile.business_name if profile else "",
        }
        case.subject_id = str(user.pk)
        VerificationDocument.objects.create(
            case=case,
            document_type=DocumentType.PAN,
            status=DocumentStatus.VERIFIED,  # format only; a reviewer checks the rest
            masked_value=last_four(pan),
        )
        if gstin:
            VerificationDocument.objects.create(
                case=case,
                document_type=DocumentType.GSTIN,
                status=DocumentStatus.VERIFIED,
                masked_value=last_four(gstin),
            )
        return _submit(case, user=user, request=request)


def submit_property(user, prop, *, request=None) -> VerificationCase:
    """A property's confirmed map pin, plus geo-tagged photos taken near it."""
    if prop.vendor_id != user.pk or prop.is_deleted:
        raise ValidationError({"property": ["No such property."]})
    if not prop.address.strip():
        raise ValidationError({"address": ["Add the property's address first."]})
    if not prop.has_point or not prop.location_confirmed:
        raise ValidationError({"location_confirmed": ["Place the map pin and confirm it."]})
    latitude, longitude = float(prop.latitude), float(prop.longitude)
    validate_in_india(latitude, longitude)

    minimum = settings.VERIFICATION_MIN_PROPERTY_PHOTOS
    max_m = settings.VERIFICATION_PHOTO_MAX_DISTANCE_M
    photos = list(prop.photos.select_related("media").exclude(media__status__in=UNUSABLE_MEDIA))
    if len(photos) < minimum:
        raise ValidationError({"photos": [f"Add at least {minimum} photos of the property."]})
    located = [p for p in photos if p.latitude is not None]
    far = [
        str(p.pk)
        for p in located
        if distance_m(latitude, longitude, float(p.latitude), float(p.longitude)) > max_m
    ]
    if far:
        raise ValidationError(
            {
                "photos": [
                    f"These photos weren't taken within {max_m} m of the pin: {', '.join(far)}."
                ]
            }
        )
    if len(located) < minimum:
        raise ValidationError(
            {"photos": [f"At least {minimum} photos need the location they were taken at."]}
        )

    with transaction.atomic():
        case = _open_for_submission(user, CheckType.PROPERTY, prop=prop)
        case.subject_id = str(prop.pk)
        case.details = {
            "pin": {"latitude": latitude, "longitude": longitude},
            "name": prop.name,
            "address": prop.address,
            "city": prop.city,
            "state": prop.state,
        }
        for photo in located:
            VerificationDocument.objects.create(
                case=case,
                document_type=DocumentType.PROPERTY_PHOTO,
                media=photo.media,
                metadata={
                    "photo_id": str(photo.pk),
                    "latitude": float(photo.latitude),
                    "longitude": float(photo.longitude),
                    "captured_at": photo.captured_at.isoformat() if photo.captured_at else "",
                    "distance_m": round(
                        distance_m(
                            latitude, longitude, float(photo.latitude), float(photo.longitude)
                        )
                    ),
                },
            )
        return _submit(case, user=user, request=request)


def submit_social(user, *, request=None) -> VerificationCase:
    """The Instagram handle on the talent profile. The reviewer looks for a code in the bio."""
    profile = getattr(user, "talent_profile", None)
    handle = profile.instagram_handle if profile and not profile.is_deleted else ""
    if not handle:
        raise ValidationError(
            {"instagram_handle": ["Add your Instagram handle to your profile first."]}
        )
    with transaction.atomic():
        case = _open_for_submission(user, CheckType.SOCIAL)
        code = case.details.get("bio_code") or f"BARTERLY-{secrets.token_hex(3).upper()}"
        case.subject_id = f"instagram:{handle.lower()}"
        case.details = {"platform": "instagram", "handle": handle, "bio_code": code}
        return _submit(case, user=user, request=request)


def submit_certificates(user, *, certificates: list[Certificate], request=None) -> VerificationCase:
    if not certificates:
        raise ValidationError({"certificates": ["Add at least one certificate."]})
    media = _own_media(user, [c.media_id for c in certificates], Kind.DOCUMENT)
    with transaction.atomic():
        case = _open_for_submission(user, CheckType.CERTIFICATE)
        case.subject_id = str(user.pk)
        case.details = {"titles": [c.title for c in certificates]}
        for cert in certificates:
            VerificationDocument.objects.create(
                case=case,
                document_type=DocumentType.CERTIFICATE,
                media=media[str(cert.media_id)],
                metadata={"title": cert.title},
            )
        return _submit(case, user=user, request=request)


def submit_reference(
    user, *, name: str, phone: str, relationship: str, request=None
) -> VerificationCase:
    """One person who can vouch for the talent. A reviewer calls them."""
    phone = normalize_phone(phone)
    if phone == user.phone:
        raise ValidationError({"phone": ["Your reference needs their own number, not yours."]})
    with transaction.atomic():
        case = _open_for_submission(user, CheckType.REFERENCE)
        case.subject_id = str(user.pk)
        case.details = {"name": name.strip(), "phone": phone, "relationship": relationship.strip()}
        return _submit(case, user=user, request=request)
