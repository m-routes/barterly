"""Request-id middleware: one id per request, in logs, audit entries and the response."""

import logging
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


class SecurityHeadersMiddleware:
    """Content-Security-Policy, Permissions-Policy and Cross-Origin-Resource-Policy.

    The API only returns JSON and files, so it gets the strictest policy: nothing may
    load, nothing may frame it. The Django admin (the back office) and, outside
    production, the Swagger docs get a policy that allows exactly what they load.
    Django's SecurityMiddleware already sets HSTS, nosniff, Referrer-Policy and COOP;
    XFrameOptionsMiddleware sets X-Frame-Options: DENY.
    """

    API_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    PERMISSIONS_POLICY = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
        "microphone=(), payment=(), usb=(), interest-cohort=()"
    )

    def __init__(self, get_response):
        from django.conf import settings

        self.get_response = get_response
        static = _origin(settings.STATIC_URL)
        media = " ".join(getattr(settings, "CSP_MEDIA_ORIGINS", []))
        self.admin_policy = "; ".join(
            [
                "default-src 'self'",
                f"script-src 'self' {static}".strip(),
                # The admin's templates use a few style attributes.
                f"style-src 'self' 'unsafe-inline' {static}".strip(),
                f"img-src 'self' data: {static} {media}".strip(),
                f"font-src 'self' {static}".strip(),
                "object-src 'none'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
            ]
        )
        # drf-spectacular's Swagger UI loads from jsDelivr and starts with an inline
        # script. Only reachable where API_DOCS_ENABLED (never production).
        self.docs_policy = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://cdn.jsdelivr.net; frame-ancestors 'none'; "
            "object-src 'none'; base-uri 'self'"
        )

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path
        if path.startswith("/admin/"):
            policy = self.admin_policy
        elif path.startswith("/api/docs/"):
            policy = self.docs_policy
        else:
            policy = self.API_POLICY
        response.headers.setdefault("Content-Security-Policy", policy)
        response.headers.setdefault("Permissions-Policy", self.PERMISSIONS_POLICY)
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response


def _origin(url: str) -> str:
    """'https://host/path/' → 'https://host'; relative URLs → ''."""
    if "://" not in url:
        return ""
    scheme, rest = url.split("://", 1)
    return f"{scheme}://{rest.split('/', 1)[0]}"


class EdgeForwardedForMiddleware:
    """Drop the load balancer's own hop from X-Forwarded-For (docs/edge.md).

    Behind the global HTTPS load balancer, Cloud Run receives
    `X-Forwarded-For: <client-supplied...>, <client>, <load balancer IP>`. DRF's
    NUM_PROXIES=1 takes the last entry, which would make every app user the same
    "client" for per-IP throttles. When the last entry is one of EDGE_PROXY_IPS, it is
    removed so the last entry is the real client again.

    Only the last entry is checked: a request straight to the run.app URL always ends in
    the caller's real address (Cloud Run appends it), so naming the load balancer
    earlier in a forged header changes nothing.
    """

    def __init__(self, get_response):
        from django.conf import settings

        self.get_response = get_response
        self.edge_ips = frozenset(getattr(settings, "EDGE_PROXY_IPS", []) or [])

    def __call__(self, request):
        if self.edge_ips:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
            if len(hops) > 1 and hops[-1] in self.edge_ips:
                request.META["HTTP_X_FORWARDED_FOR"] = ", ".join(hops[:-1])
        return self.get_response(request)


class DeprecationMiddleware:
    """Deprecation, Sunset and Link headers on deprecated operations
    (apps.common.deprecation, docs/api-versioning.md).

    Each call to one is also logged with the app's platform and version, so we can see
    who still uses it before raising the minimum app version:
    `jsonPayload.deprecated_call=true` in Cloud Logging.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from apps.common.deprecation import headers_for

        response = self.get_response(request)
        headers = headers_for(request.method, request.path)
        if headers:
            for name, value in headers.items():
                response.headers.setdefault(name, value)
            logging.getLogger("apps.api").info(
                "Deprecated API call",
                extra={
                    "deprecated_call": True,
                    "method": request.method,
                    "path": request.path,
                    "sunset": headers["Sunset"],
                    "client_platform": request.META.get("HTTP_X_CLIENT_PLATFORM", "")[:20],
                    "client_version": request.META.get("HTTP_X_CLIENT_VERSION", "")[:40],
                },
            )
        return response
