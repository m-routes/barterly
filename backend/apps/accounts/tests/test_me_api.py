import pytest
from django.urls import reverse

from apps.accounts.tests.factories import VendorFactory

pytestmark = pytest.mark.django_db
URL = reverse("accounts:me")


def test_anonymous_gets_error_shape(client):
    response = client.get(URL)
    assert response.status_code == 401
    assert response.json() == {
        "code": "not_authenticated",
        "message": "Authentication credentials were not provided.",
        "details": {},
    }


def test_signed_in_user_sees_themselves(client):
    user = VendorFactory(email="host@example.com")
    client.force_login(user)
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.pk),
        "phone": user.phone,
        "email": "host@example.com",
        "role": "vendor",
        "is_active": True,
        "profile_complete": False,
        "created_at": response.json()["created_at"],
    }
    assert response["X-Request-ID"]


def test_basic_auth_is_not_accepted(client):
    user = VendorFactory()
    import base64

    token = base64.b64encode(f"{user.phone}:test-password-123".encode()).decode()
    response = client.get(URL, HTTP_AUTHORIZATION=f"Basic {token}")
    assert response.status_code == 401
