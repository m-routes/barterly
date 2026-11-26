"""Consent: give and withdraw, one purpose at a time, each tied to a document version.

Withdrawing is the same call as giving (granted=False). Terms and the privacy policy
are required to use Barterly, so they can't be withdrawn on their own: that is what
deleting the account does (apps.privacy.services.erasure).
"""

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.privacy.models import REQUIRED_PURPOSES, ConsentRecord, ConsentSource, Purpose


class ConsentError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class ConsentState:
    purpose: str
    label: str
    required: bool
    granted: bool
    version: str  # the version agreed to (or withdrawn), "" if never asked
    current_version: str
    recorded_at: datetime | None

    @property
    def needs_renewal(self) -> bool:
        """Given, but for an older version of the document."""
        return self.granted and self.version != self.current_version


def current_version(purpose: str) -> str:
    return settings.PRIVACY_DOCUMENT_VERSIONS[purpose]


def latest(user, purpose: str) -> ConsentRecord | None:
    return ConsentRecord.objects.filter(user=user, purpose=purpose).first()


def has_consent(user, purpose: str) -> bool:
    """True if the newest record for this purpose gives consent (any version)."""
    if user is None or not getattr(user, "pk", None):
        return False
    record = latest(user, purpose)
    return bool(record and record.granted)


def withdrawn(user, purpose: str) -> bool:
    """True only if the person said no (as opposed to never being asked)."""
    record = latest(user, purpose)
    return bool(record and not record.granted)


def states(user) -> list[ConsentState]:
    newest: dict[str, ConsentRecord] = {}
    for record in ConsentRecord.objects.filter(user=user).order_by(
        "purpose", "-recorded_at", "-id"
    ):
        newest.setdefault(record.purpose, record)
    result = []
    for purpose in Purpose:
        record = newest.get(purpose.value)
        result.append(
            ConsentState(
                purpose=purpose.value,
                label=purpose.label,
                required=purpose in REQUIRED_PURPOSES,
                granted=bool(record and record.granted),
                version=record.version if record else "",
                current_version=current_version(purpose.value),
                recorded_at=record.recorded_at if record else None,
            )
        )
    return result


def record(
    user,
    purpose: str,
    *,
    granted: bool,
    version: str | None = None,
    source: str = ConsentSource.API,
    request=None,
    allow_required_withdrawal: bool = False,
    now=None,
) -> ConsentRecord:
    """Give or withdraw one consent. A version, when sent, must be the current one, so
    nobody agrees to a text they weren't shown."""
    if purpose not in Purpose.values:
        raise ConsentError("unknown_purpose", f"Unknown purpose: {purpose}.")
    expected = current_version(purpose)
    if granted and version is not None and version != expected:
        raise ConsentError(
            "document_changed",
            "This document has changed since you opened it. Read the new version first.",
            409,
        )
    if not granted and purpose in REQUIRED_PURPOSES and not allow_required_withdrawal:
        raise ConsentError(
            "consent_required",
            "The terms and the privacy policy are needed to use Barterly. "
            "To withdraw them, delete your account.",
            409,
        )
    now = now or timezone.now()
    with transaction.atomic():
        previous = latest(user, purpose)
        entry = ConsentRecord.objects.create(
            user=user,
            purpose=purpose,
            granted=granted,
            version=expected
            if granted
            else (version or (previous.version if previous else expected)),
            source=source,
            recorded_at=now,
        )
        log_action(
            actor=user,
            action="privacy.consent_given" if granted else "privacy.consent_withdrawn",
            obj=user,
            before={
                "purpose": purpose,
                "granted": previous.granted if previous else None,
                "version": previous.version if previous else None,
            },
            after={
                "purpose": purpose,
                "granted": granted,
                "version": entry.version,
                "source": source,
            },
            request=request,
        )
        publish(
            DomainEvent(
                "privacy.consent_changed",
                {"user_id": user.pk, "purpose": purpose, "granted": granted},
                occurred_at=now,
            )
        )
    return entry


def record_sign_up(user, *, terms_version: str, privacy_version: str, source: str, request=None):
    """The two required consents, taken together at sign-up but recorded separately."""
    record(user, Purpose.TERMS, granted=True, version=terms_version, source=source, request=request)
    record(
        user, Purpose.PRIVACY, granted=True, version=privacy_version, source=source, request=request
    )


def needs_required_consent(user) -> bool:
    """True if the terms or privacy policy were never given, withdrawn, or changed since."""
    if user is None or not getattr(user, "pk", None):
        return True
    for purpose in REQUIRED_PURPOSES:
        record = latest(user, purpose)
        if record is None or not record.granted or record.version != current_version(purpose):
            return True
    return False
