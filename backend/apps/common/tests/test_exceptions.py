import json
import logging

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.test import RequestFactory
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.common import views as error_views
from apps.common.exceptions import SERVER_ERROR_MESSAGE

factory = APIRequestFactory()


def raising_view(exc):
    class View(APIView):
        permission_classes = [AllowAny]
        authentication_classes = []

        def get(self, request):
            raise exc

    return View.as_view()


def call(exc):
    response = raising_view(exc)(factory.get("/api/test/"))
    return response.status_code, response.data


@pytest.mark.parametrize(
    ("exc", "status", "body"),
    [
        (
            exceptions.ValidationError({"phone": ["Enter a valid phone number."]}),
            400,
            {
                "code": "validation_error",
                "message": "Invalid input.",
                "details": {"phone": ["Enter a valid phone number."]},
            },
        ),
        (
            exceptions.ValidationError(["Dates overlap."]),
            400,
            {
                "code": "validation_error",
                "message": "Invalid input.",
                "details": {"non_field_errors": ["Dates overlap."]},
            },
        ),
        (
            DjangoValidationError({"email": "Taken."}),
            400,
            {
                "code": "validation_error",
                "message": "Invalid input.",
                "details": {"email": ["Taken."]},
            },
        ),
        (exceptions.NotFound(), 404, {"code": "not_found", "message": "Not found.", "details": {}}),
        (Http404("x"), 404, {"code": "not_found", "message": "Not found.", "details": {}}),
        (
            DjangoPermissionDenied(),
            403,
            {
                "code": "permission_denied",
                "message": "You do not have permission to perform this action.",
                "details": {},
            },
        ),
        (
            # Session auth sends no WWW-Authenticate challenge, so DRF answers 403.
            exceptions.NotAuthenticated(),
            403,
            {
                "code": "not_authenticated",
                "message": "Authentication credentials were not provided.",
                "details": {},
            },
        ),
        (
            exceptions.PermissionDenied("Vendors only.", code="vendor_only"),
            403,
            {"code": "vendor_only", "message": "Vendors only.", "details": {}},
        ),
    ],
)
def test_errors_use_one_shape(exc, status, body):
    assert call(exc) == (status, body)


def test_throttled_includes_retry_after():
    status, body = call(exceptions.Throttled(wait=12.4))
    assert status == 429
    assert body["code"] == "throttled"
    assert body["details"] == {"retry_after_seconds": 13}  # DRF rounds the wait up


def test_unhandled_exception_becomes_json_500_and_is_logged(caplog):
    with caplog.at_level(logging.ERROR, logger="apps.api"):
        status, body = call(RuntimeError("boom"))
    assert status == 500
    assert body == {"code": "server_error", "message": SERVER_ERROR_MESSAGE, "details": {}}
    assert "Unhandled API exception" in caplog.text
    assert "RuntimeError: boom" in caplog.text


def test_successful_responses_are_untouched():
    class View(APIView):
        permission_classes = [AllowAny]

        def get(self, request):
            return Response({"ok": True})

    assert View.as_view()(factory.get("/")).data == {"ok": True}


class TestDjangoErrorHandlers:
    rf = RequestFactory()

    def test_api_404_is_json(self):
        response = error_views.not_found(self.rf.get("/api/v1/nope/"), Http404())
        assert response.status_code == 404
        assert json.loads(response.content) == {
            "code": "not_found",
            "message": "Not found.",
            "details": {},
        }

    def test_api_500_is_json(self):
        response = error_views.server_error(self.rf.get("/api/v1/x/"))
        assert response.status_code == 500
        assert json.loads(response.content)["code"] == "server_error"

    def test_non_api_paths_keep_django_pages(self):
        assert error_views.not_found(self.rf.get("/admin/x"), Http404()).status_code == 404
        response = error_views.server_error(self.rf.get("/admin/x"))
        assert response.status_code == 500
        assert response["Content-Type"].startswith("text/html")


@pytest.mark.django_db
def test_unknown_api_url_returns_json_404(client, settings):
    settings.DEBUG = False
    response = client.get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
