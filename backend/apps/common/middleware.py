"""Request-id middleware: one id per request, in logs, audit entries and the response."""

import re
import uuid

from apps.common.request_context import reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"
# Accept a caller-supplied id only if it is short and harmless to log.
_VALID_ID = re.compile(r"^[A-Za-z0-9._\-]{8,128}$")
# Cloud Run sets X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=1
_TRACE = re.compile(r"^([0-9a-fA-F]{32})/")


def resolve_request_id(meta: dict) -> str:
    """Pick the incoming X-Request-ID, else the Cloud Run trace id, else a new uuid."""
    incoming = meta.get("HTTP_X_REQUEST_ID", "")
    if _VALID_ID.match(incoming):
        return incoming
    trace = _TRACE.match(meta.get("HTTP_X_CLOUD_TRACE_CONTEXT", ""))
    if trace:
        return trace.group(1).lower()
    return uuid.uuid4().hex


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = resolve_request_id(request.META)
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            _tag_sentry(request_id)
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


def _tag_sentry(request_id: str) -> None:
    # No-op unless Sentry was initialised (config.sentry).
    import sentry_sdk

    sentry_sdk.set_tag("request_id", request_id)
