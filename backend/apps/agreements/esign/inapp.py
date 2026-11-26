"""Signing in the app: explicit consent plus a fresh OTP re-confirmation.

The client re-runs phone OTP sign-in (Firebase) just before signing and sends the new ID
token. We check it with the same verifier as sign-in (settings.AUTH_TOKEN_VERIFIER): it
must prove the signer's own phone number, and the OTP must have been completed within
OTP_MAX_AGE. Together with the time, IP address and device, that is the signature's
evidence.
"""

import uuid
from datetime import timedelta

from apps.accounts.auth.verifiers import InvalidSignInToken, VerifierUnavailable, get_verifier
from apps.agreements.esign.base import (
    Challenge,
    ProviderUnavailable,
    SignatureEvidence,
    SigningAttempt,
    SigningRefused,
    consent_text,
    mask_phone,
)

OTP_MAX_AGE = timedelta(minutes=5)


class InAppESignProvider:
    name = "in_app_otp"

    def challenge(self, *, version, signer) -> Challenge:
        return Challenge(
            method="otp",
            consent_text=consent_text(version),
            phone_hint=mask_phone(signer.phone or ""),
            max_age_seconds=int(OTP_MAX_AGE.total_seconds()),
        )

    def sign(self, attempt: SigningAttempt) -> SignatureEvidence:
        if not attempt.consent:
            raise SigningRefused("Tick the box to agree before signing.")
        if not attempt.otp_token:
            raise SigningRefused("Confirm your phone number with a one-time code to sign.")
        try:
            identity = get_verifier().verify(attempt.otp_token)
        except InvalidSignInToken as exc:
            raise SigningRefused("That confirmation didn't work. Get a new code.") from exc
        except VerifierUnavailable as exc:
            raise ProviderUnavailable(str(exc)) from exc
        if identity.phone != attempt.signer.phone:
            raise SigningRefused("Confirm with the phone number on your Barterly account.")
        if identity.auth_time is None or attempt.now - identity.auth_time > OTP_MAX_AGE:
            minutes = int(OTP_MAX_AGE.total_seconds() // 60)
            raise SigningRefused(
                f"Confirm your phone again: the code must be from the last {minutes} minutes."
            )
        return SignatureEvidence(
            provider=self.name,
            reference=str(uuid.uuid4()),
            phone=identity.phone,
            otp_verified_at=identity.auth_time,
            extra={"otp_provider": identity.provider, "otp_uid": identity.provider_uid},
        )
