"""Who may call the job endpoints: Cloud Scheduler, and nobody else.

Cloud Scheduler sends a Google-signed OIDC ID token (Authorization: Bearer ...) for
the scheduler service account. We check Google's signature, that the audience is this
API, and that the caller is that service account. Terraform sets SCHEDULER_AUDIENCE
and SCHEDULER_INVOKER_EMAIL (infra/terraform/modules/environment/scheduler.tf).
"""

from django.conf import settings
from django.utils.module_loading import import_string


class SchedulerAuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


class GoogleOidcVerifier:
    """Checks a Google-signed OIDC token for an audience and one service account. The
    defaults are the scheduler's; the task endpoint passes the tasks account's."""

    def verify(self, token: str, *, audience: str = "", email: str = "") -> dict:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        audience = audience or settings.SCHEDULER_AUDIENCE
        email = email or settings.SCHEDULER_INVOKER_EMAIL
        if not audience or not email:
            raise SchedulerAuthError("Scheduled jobs aren't configured here.", status=503)
        try:
            claims = id_token.verify_oauth2_token(
                token, google_requests.Request(), audience=audience
            )
        except ValueError as exc:  # bad signature, expired, wrong audience
            raise SchedulerAuthError("Invalid scheduler token.") from exc
        if claims.get("email") != email or not claims.get("email_verified"):
            raise SchedulerAuthError("This caller may not run jobs.", status=403)
        return claims


def _bearer(request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise SchedulerAuthError("Missing scheduler token.")
    return token


def verify_request(request) -> dict:
    return import_string(settings.SCHEDULER_TOKEN_VERIFIER)().verify(_bearer(request))


def verify_task_request(request) -> dict:
    """Cloud Tasks calls with an OIDC token for the tasks service account."""
    return import_string(settings.SCHEDULER_TOKEN_VERIFIER)().verify(
        _bearer(request),
        audience=settings.TASKS_AUDIENCE,
        email=settings.TASKS_INVOKER_EMAIL,
    )
