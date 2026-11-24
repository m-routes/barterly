"""Turn service errors into API errors with the shared {code, message, details} shape."""

from rest_framework import exceptions


class PrivacyAPIError(exceptions.APIException):
    def __init__(self, *, code: str, message: str, status: int, details: dict | None = None):
        super().__init__(message, code)
        self.status_code = status
        self.default_code = code
        if details:
            self.extra_details = details


def consent_error(exc) -> PrivacyAPIError:
    return PrivacyAPIError(code=exc.code, message=exc.message, status=exc.status)


def service_error(exc) -> PrivacyAPIError:
    return PrivacyAPIError(
        code=exc.code, message=exc.message, status=exc.status, details=getattr(exc, "details", None)
    )
