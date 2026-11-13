"""FirebaseTokenVerifier with firebase_admin's verify call mocked: no network, ever."""

from unittest import mock

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
    assert FirebaseTokenVerifier(project_id="barterly-test").app is verifier.app


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
