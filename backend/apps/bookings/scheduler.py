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
    def verify(self, token: str) -> dict:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        if not settings.SCHEDULER_AUDIENCE or not settings.SCHEDULER_INVOKER_EMAIL:
            raise SchedulerAuthError("Scheduled jobs aren't configured here.", status=503)
        try:
            claims = id_token.verify_oauth2_token(
                token, google_requests.Request(), audience=settings.SCHEDULER_AUDIENCE
            )
        except ValueError as exc:  # bad signature, expired, wrong audience
            raise SchedulerAuthError("Invalid scheduler token.") from exc
        if claims.get("email") != settings.SCHEDULER_INVOKER_EMAIL or not claims.get(
            "email_verified"
        ):
            raise SchedulerAuthError("This caller may not run jobs.", status=403)
        return claims


def verify_request(request) -> dict:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise SchedulerAuthError("Missing scheduler token.")
    return import_string(settings.SCHEDULER_TOKEN_VERIFIER)().verify(token)
