"""Test-only stand-in for the OTP provider. Never referenced by deployed settings."""

from datetime import UTC, datetime

from django.utils import timezone

from apps.accounts.auth.verifiers import InvalidSignInToken, VerifierUnavailable, identity

PREFIX = "fake-otp:"
UNAVAILABLE = "fake-otp:unavailable"


def token_for(phone: str, *, at: datetime | None = None) -> str:
    """The token a client would get after completing the OTP for `phone` (now, or `at`)."""
    return f"{PREFIX}{phone}" + (f"@{int(at.timestamp())}" if at else "")


class FakeTokenVerifier:
    """Accepts `fake-otp:<phone>[@<unix time of the OTP>]`; anything else is invalid."""

    provider = "fake"

    def verify(self, token: str):
        if token == UNAVAILABLE:
            raise VerifierUnavailable("fake outage")
        if not token.startswith(PREFIX):
            raise InvalidSignInToken("not a fake token")
        phone, _, when = token.removeprefix(PREFIX).partition("@")
        auth_time = datetime.fromtimestamp(int(when), UTC) if when else timezone.now()
        return identity(
            phone=phone, provider=self.provider, provider_uid=f"fake-{phone}", auth_time=auth_time
        )
