"""FirebaseTokenVerifier with firebase_admin's verify call mocked: no network, ever."""

from unittest import mock

import google.auth.exceptions
import pytest
from django.conf import settings
from firebase_admin import auth

from apps.accounts.auth.verifiers import (
    FirebaseTokenVerifier,
    InvalidSignInToken,
    VerifiedIdentity,
    VerifierUnavailable,
    get_verifier,
)
from apps.accounts.tests.fakes import FakeTokenVerifier

VERIFY = "firebase_admin.auth.verify_id_token"


def claims(**overrides):
    base = {
        "uid": "fb-uid-1",
        "phone_number": "+919876543210",
        "firebase": {"sign_in_provider": "phone"},
    }
    return {**base, **overrides}


@pytest.fixture
def verifier():
    return FirebaseTokenVerifier(project_id="barterly-test", check_revoked=True)


def test_phone_token_is_accepted(verifier):
    with mock.patch(VERIFY, return_value=claims()) as verify:
        result = verifier.verify("id-token")
    assert result == VerifiedIdentity(
        phone="+919876543210", provider="firebase", provider_uid="fb-uid-1"
    )
    verify.assert_called_once_with("id-token", app=verifier.app, check_revoked=True)
    assert verifier.app.project_id == "barterly-test"


def test_app_is_reused_across_instances(verifier):
    again = FirebaseTokenVerifier(project_id="barterly-test", check_revoked=True)
    assert again.app is verifier.app


def no_default_credentials():
    error = google.auth.exceptions.DefaultCredentialsError("no ADC on this machine")
    return mock.patch("google.auth.default", side_effect=error)


def test_without_revocation_check_no_google_credentials_are_needed():
    # A laptop has no Application Default Credentials; checking signatures must still work.
    keys_only = FirebaseTokenVerifier(project_id="barterly-keys", check_revoked=False)
    with no_default_credentials():
        client = auth._get_client(keys_only.app)
    assert client is not None
    assert keys_only.app.project_id == "barterly-keys"


def test_revocation_check_uses_default_credentials():
    revoking = FirebaseTokenVerifier(project_id="barterly-adc", check_revoked=True)
    with no_default_credentials(), pytest.raises(google.auth.exceptions.DefaultCredentialsError):
        auth._get_client(revoking.app)


@pytest.mark.parametrize(
    "bad_claims",
    [
        claims(firebase={"sign_in_provider": "password"}),
        claims(firebase={}),
        claims(phone_number=None),
        claims(phone_number="12"),
    ],
)
def test_non_phone_tokens_are_rejected(verifier, bad_claims):
    with mock.patch(VERIFY, return_value=bad_claims), pytest.raises(InvalidSignInToken):
        verifier.verify("id-token")


@pytest.mark.parametrize(
    "error",
    [
        ValueError("malformed"),
        auth.InvalidIdTokenError("bad signature"),
        auth.ExpiredIdTokenError("expired", cause=None),
        auth.RevokedIdTokenError("revoked"),
        auth.UserDisabledError("disabled"),
    ],
)
def test_firebase_rejections_become_invalid_token(verifier, error):
    with mock.patch(VERIFY, side_effect=error), pytest.raises(InvalidSignInToken):
        verifier.verify("id-token")


def test_certificate_fetch_failure_is_unavailable(verifier):
    error = auth.CertificateFetchError("no certs", cause=None)
    with mock.patch(VERIFY, side_effect=error), pytest.raises(VerifierUnavailable):
        verifier.verify("id-token")


def test_firebase_is_the_configured_verifier_outside_tests():
    # The autouse fixture swaps in the fake; the real setting must name Firebase.
    from config.settings import base

    assert base.AUTH_TOKEN_VERIFIER.endswith("FirebaseTokenVerifier")
    assert settings.AUTH_TOKEN_VERIFIER.endswith("FakeTokenVerifier")


def test_get_verifier_builds_once():
    first = get_verifier()
    assert isinstance(first, FakeTokenVerifier)
    assert get_verifier() is first
