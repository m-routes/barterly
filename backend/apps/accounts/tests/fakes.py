"""Test-only stand-in for the OTP provider. Never referenced by deployed settings."""

from apps.accounts.auth.verifiers import InvalidSignInToken, VerifierUnavailable, identity

PREFIX = "fake-otp:"
UNAVAILABLE = "fake-otp:unavailable"


def token_for(phone: str) -> str:
    """The token a client would get after completing the OTP for `phone`."""
    return f"{PREFIX}{phone}"


class FakeTokenVerifier:
    """Accepts `fake-otp:<phone>`; anything else is an invalid token."""

    provider = "fake"

    def verify(self, token: str):
        if token == UNAVAILABLE:
            raise VerifierUnavailable("fake outage")
        if not token.startswith(PREFIX):
            raise InvalidSignInToken("not a fake token")
        phone = token.removeprefix(PREFIX)
        return identity(phone=phone, provider=self.provider, provider_uid=f"fake-{phone}")
