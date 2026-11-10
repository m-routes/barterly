from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.services.health import HealthReport


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_health_ok(api_client):
    response = api_client.get(reverse("core:health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_degraded_returns_503(api_client):
    with mock.patch("apps.core.views.get_health_report", return_value=HealthReport(database=False)):
        response = api_client.get(reverse("core:health"))
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@pytest.mark.django_db
def test_openapi_schema_lists_health_endpoint(api_client):
    response = api_client.get(reverse("schema"), HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    assert "/api/v1/health/" in response.json()["paths"]
