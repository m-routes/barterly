"""Stand-ins the seed uses instead of real providers, so seeding never moves money,
sends signing codes or calls Razorpay. Everything they produce is labelled
"staging_seed" or prefixed "seed_", so seeded records can't be mistaken for real ones.
"""

import uuid
from contextlib import contextmanager

from django.test import override_settings

from apps.agreements.esign.base import (
    Challenge,
    SignatureEvidence,
    SigningAttempt,
    SigningRefused,
    consent_text,
)

SEED_WEBHOOK_SECRET = "staging-seed-webhook-secret"  # signs fake events only; not a secret  # nosec B105  # noqa: S105


class SeedESignProvider:
    """Records consent for seeded agreements. Never configured outside the seed."""

    name = "staging_seed"

    def challenge(self, *, version, signer) -> Challenge:
        return Challenge(method="none", consent_text=consent_text(version))

    def sign(self, attempt: SigningAttempt) -> SignatureEvidence:
        if not attempt.consent:
            raise SigningRefused("Seeded signatures still need consent.")
        return SignatureEvidence(
            provider=self.name,
            reference=f"seed-{uuid.uuid4()}",
            phone=attempt.signer.phone or "",
            extra={"seeded": True},
        )


def _clear_caches() -> None:
    from apps.agreements.esign import base as esign
    from apps.money.gateway import base as escrow_gateway
    from apps.money.gateway import payouts as payout_provider

    esign._build.cache_clear()
    escrow_gateway._build.cache_clear()
    payout_provider._build.cache_clear()


@contextmanager
def seed_providers():
    """Swap signing and payment providers for stand-ins for the duration of a seed."""
    with override_settings(
        ESIGN_PROVIDER="apps.qa.providers.SeedESignProvider",
        ESCROW_GATEWAY="apps.money.gateway.fake.FakeEscrowGateway",
        PAYOUT_PROVIDER="apps.money.gateway.fake.FakePayoutProvider",
        RAZORPAY_ESCROW_WEBHOOK_SECRET=SEED_WEBHOOK_SECRET,
    ):
        _clear_caches()
        try:
            yield
        finally:
            _clear_caches()
    _clear_caches()
