"""Turn away apps older than the minimum supported version (docs/api-versioning.md).

The mobile app sends `X-Client-Platform: android|ios` and `X-Client-Version: 1.4.2` on
every call. Below the platform's minimum, every API path answers 426 with code
`upgrade_required`, and the app shows its blocking update screen. Requests without the
headers (the web console, webhooks, Cloud Tasks) are never affected.
"""

import re

from django.http import JsonResponse

from apps.appversions import services
from apps.common.exceptions import error_body

PLATFORM_HEADER = "HTTP_X_CLIENT_PLATFORM"
VERSION_HEADER = "HTTP_X_CLIENT_VERSION"
UPGRADE_REQUIRED = "upgrade_required"

# Paths an outdated app must still reach: the version check itself and the probes.
_EXEMPT = re.compile(r"^/api/v1/(app/version|health)/")


class ClientVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        platform = request.META.get(PLATFORM_HEADER, "").strip().lower()
        version = request.META.get(VERSION_HEADER, "")
        if platform and request.path.startswith("/api/") and not _EXEMPT.match(request.path):
            policy = services.upgrade_required(platform, version)
            if policy is not None:
                return JsonResponse(
                    error_body(
                        UPGRADE_REQUIRED,
                        policy.message
                        or "This version of Barterly is no longer supported. Update to continue.",
                        {"minimum_version": policy.minimum_version, "store_url": policy.store_url},
                    ),
                    status=426,
                )
        return self.get_response(request)
