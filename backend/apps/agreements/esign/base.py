"""The e-signature provider interface.

A provider proves that a person consented to one exact document. The services hand it
a SigningAttempt (who, which version and its PDF fingerprint, what they sent and where
from) and get back SignatureEvidence to store, or SigningRefused.

InAppESignProvider (esign.inapp) is the one we ship: consent plus a fresh OTP
re-confirmation of the signer's phone. FakeESignProvider (esign.fake) is for tests. A
third-party provider (Aadhaar eSign, DocuSign, ...) would be another class here. The
class is a code setting (ESIGN_PROVIDER), so a deployed service can't be pointed at the
fake from the environment.
"""

from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from typing import Any, Protocol

from django.conf import settings
from django.utils.module_loading import import_string

# PLACEHOLDER LEGAL TEXT: a lawyer must review this wording before launch (with the
# agreement template, apps/agreements/templates/agreements/).
CONSENT_TEXT = (
    "I have read version {number} of this agreement (document fingerprint {fingerprint}) "
    "and I agree to its terms. I understand that signing electronically binds me as a "
    "handwritten signature would."
)


def consent_text(version) -> str:
    return CONSENT_TEXT.format(number=version.number, fingerprint=version.pdf_sha256[:16])


@dataclass(frozen=True)
class Challenge:
    """What the client must do to sign."""

    method: str  # "otp": re-confirm the phone by OTP and send the ID token; "none"
    consent_text: str
    phone_hint: str = ""  # e.g. "+91 ••••• •4321"
    max_age_seconds: int = 0  # how fresh the OTP must be


@dataclass(frozen=True)
class SigningAttempt:
    version: Any  # AgreementVersion
    signer: Any  # User
    party: str
    consent: bool
    otp_token: str
    ip: str | None
    user_agent: str
    device: str
    now: datetime


@dataclass(frozen=True)
class SignatureEvidence:
    provider: str
    reference: str
    phone: str = ""
    otp_verified_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class SigningRefused(Exception):
    """The attempt doesn't prove consent (the message says why, for the signer)."""


class ProviderUnavailable(Exception):
    """The provider (or the OTP service behind it) could not be reached."""


class ESignProvider(Protocol):
    name: str

    def challenge(self, *, version, signer) -> Challenge:
        """What the signer must do for this version."""
        ...

    def sign(self, attempt: SigningAttempt) -> SignatureEvidence:
        """Check the attempt and return the evidence to keep. Raises SigningRefused."""
        ...


def mask_phone(phone: str) -> str:
    if len(phone) < 7:
        return "•" * len(phone)
    return f"{phone[:3]} {'•' * (len(phone) - 7)} {phone[-4:]}"


@cache
def _build(path: str) -> ESignProvider:
    return import_string(path)()


def get_provider() -> ESignProvider:
    """The provider named by settings.ESIGN_PROVIDER (built once per process)."""
    return _build(settings.ESIGN_PROVIDER)
