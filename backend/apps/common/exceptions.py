"""One error shape for every API failure: {"code", "message", "details"}.

- code: stable, machine-readable snake_case (e.g. "validation_error", "not_found").
- message: short human-readable summary.
- details: object with extra context; field errors for validation, {} otherwise.
"""

import logging

import sentry_sdk
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger("apps.api")

SERVER_ERROR_MESSAGE = "Something went wrong on our side. Quote the request id if you contact us."


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"code": code, "message": message, "details": details or {}}


def exception_handler(exc, context):
    """DRF EXCEPTION_HANDLER that renders every error as {code, message, details}."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unexpected error: log it with the traceback, report it, and return a JSON 500
        # instead of Django's HTML page.
        set_rollback()
        logger.error("Unhandled API exception", exc_info=exc)
        sentry_sdk.capture_exception(exc)
        return Response(
            error_body("server_error", SERVER_ERROR_MESSAGE),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    response.data = _format(exc)
    return response


def _format(exc: exceptions.APIException) -> dict:
    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        details = detail if isinstance(detail, dict) else {"non_field_errors": detail}
        return error_body("validation_error", "Invalid input.", details)

    codes = exc.get_codes()
    code = codes if isinstance(codes, str) else exc.default_code
    details = {}
    if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
        details["retry_after_seconds"] = int(exc.wait)
    message = exc.detail if isinstance(exc.detail, str) else str(exc.default_detail)
    return error_body(code, str(message), details)
