"""Verifying a sign-in token from the OTP provider.

The exchange endpoint only depends on the TokenVerifier interface: it hands over the
token the client got from the provider and receives a verified phone number. Firebase
phone auth is the provider today; to swap it, write another verifier and point the
AUTH_TOKEN_VERIFIER setting at it.
"""

from dataclasses import dataclass
from functools import cache
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.module_loading import import_string

from apps.accounts.services.phone import normalize_phone


@dataclass(frozen=True)
class VerifiedIdentity:
    phone: str  # E.164
    provider: str  # e.g. "firebase"
    provider_uid: str  # the provider's id for this person


class InvalidSignInToken(Exception):
    """The token is malformed, expired, revoked, or not a phone sign-in."""


class VerifierUnavailable(Exception):
    """The provider could not be reached (e.g. its signing certificates failed to load)."""


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedIdentity:
        """Return the identity the token proves.

        Raises InvalidSignInToken for a bad token and VerifierUnavailable when the
        provider itself fails.
        """
        ...


def identity(*, phone: str | None, provider: str, provider_uid: str) -> VerifiedIdentity:
    """Build a VerifiedIdentity, rejecting tokens without a usable phone number."""
    try:
        normalized = normalize_phone(phone or "")
    except ValidationError as exc:
        raise InvalidSignInToken("The token has no valid phone number.") from exc
    return VerifiedIdentity(phone=normalized, provider=provider, provider_uid=provider_uid)


def _public_keys_only_credential():
    """A firebase_admin credential that grants nothing: enough to check signatures."""
    from firebase_admin import credentials
    from google.auth.credentials import AnonymousCredentials

    class PublicKeysOnly(credentials.Base):
        def get_credential(self):
            return AnonymousCredentials()

    return PublicKeysOnly()


class FirebaseTokenVerifier:
    """Verifies Firebase Auth ID tokens from phone (SMS OTP) sign-in.

    Checking a token's signature only needs Google's public signing certificates, so
    with a project id and no revocation check the verifier runs without any Google
    credentials (a laptop works as well as Cloud Run). The revocation check calls the
    Firebase Auth API and so uses the runtime's default credentials; they also supply
    the project when FIREBASE_PROJECT_ID is unset.
    """

    provider = "firebase"

    def __init__(self, *, project_id: str | None = None, check_revoked: bool | None = None):
        import firebase_admin

        project_id = project_id or settings.FIREBASE_PROJECT_ID or None
        self.check_revoked = (
            settings.FIREBASE_CHECK_REVOKED if check_revoked is None else check_revoked
        )
        keys_only = bool(project_id) and not self.check_revoked
        mode = "keys" if keys_only else "adc"
        name = f"barterly-auth-{project_id or 'default'}-{mode}"
        try:
            self.app = firebase_admin.get_app(name)
        except ValueError:
            options = {"projectId": project_id} if project_id else None
            credential = _public_keys_only_credential() if keys_only else None
            self.app = firebase_admin.initialize_app(
                credential=credential, options=options, name=name
            )

    def verify(self, token: str) -> VerifiedIdentity:
        from firebase_admin import auth

        try:
            claims = auth.verify_id_token(token, app=self.app, check_revoked=self.check_revoked)
        except (ValueError, auth.InvalidIdTokenError, auth.UserDisabledError) as exc:
            # Expired, revoked and bad-certificate errors subclass InvalidIdTokenError.
            raise InvalidSignInToken(str(exc)) from exc
        except auth.CertificateFetchError as exc:
            raise VerifierUnavailable(str(exc)) from exc
        sign_in_provider = claims.get("firebase", {}).get("sign_in_provider")
        if sign_in_provider != "phone":
            raise InvalidSignInToken("Only phone sign-in is accepted.")
        return identity(
            phone=claims.get("phone_number"), provider=self.provider, provider_uid=claims["uid"]
        )


@cache
def _build(path: str) -> TokenVerifier:
    return import_string(path)()


def get_verifier() -> TokenVerifier:
    """The verifier named by settings.AUTH_TOKEN_VERIFIER (built once per process)."""
    return _build(settings.AUTH_TOKEN_VERIFIER)
