"""An e-sign provider for tests. Needs consent, proves nothing else. Never deployed."""

import uuid

from apps.agreements.esign.base import (
    Challenge,
    SignatureEvidence,
    SigningAttempt,
    SigningRefused,
    consent_text,
)


class FakeESignProvider:
    name = "fake"

    def __init__(self) -> None:
        self.signed: list[SigningAttempt] = []

    def challenge(self, *, version, signer) -> Challenge:
        return Challenge(method="none", consent_text=consent_text(version))

    def sign(self, attempt: SigningAttempt) -> SignatureEvidence:
        if not attempt.consent:
            raise SigningRefused("Tick the box to agree before signing.")
        self.signed.append(attempt)
        return SignatureEvidence(provider=self.name, reference=f"fake-{uuid.uuid4()}")
