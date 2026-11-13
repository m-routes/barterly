"""Rate limits for the token exchange.

Per IP (checked before the token is verified, so token guessing is capped) and per
phone (checked after, keyed on a hash so phone numbers stay out of the cache).
Rates live in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]; counters live in the shared
cache, so they hold across Cloud Run instances.
"""

import hashlib

from rest_framework.throttling import SimpleRateThrottle


class ExchangeIPThrottle(SimpleRateThrottle):
    scope = "auth_exchange_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class ExchangePhoneThrottle(SimpleRateThrottle):
    """Keyed on `request.verified_phone`, which the view sets after verifying the token."""

    scope = "auth_exchange_phone"

    def get_cache_key(self, request, view):
        phone = getattr(request, "verified_phone", None)
        if not phone:
            return None
        digest = hashlib.sha256(phone.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
