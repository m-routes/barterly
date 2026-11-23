"""Optional Sentry error reporting.

Enabled only when SENTRY_ENABLED is truthy and SENTRY_DSN is set. The DSN belongs in
Secret Manager, never in code. PII is not sent (phone numbers are user identifiers):
send_default_pii is off, local variables are not captured, and every event,
transaction and breadcrumb goes through apps.common.redaction before it leaves.
"""

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from config.settings.env import env_bool, env_float, env_str

# Kept as-is: they hold code locations and Sentry's own metadata, never user data.
_KEEP = {
    "event_id",
    "timestamp",
    "platform",
    "level",
    "logger",
    "release",
    "environment",
    "sdk",
    "modules",
    "fingerprint",
    "contexts",
    "tags",
}


def scrub_event(event, hint=None):
    """before_send / before_send_transaction: redact the user's data in the event."""
    from apps.common.redaction import redact

    scrubbed = {k: (v if k in _KEEP else redact(v)) for k, v in event.items()}
    user = event.get("user") or {}
    # Keep only the opaque id, so an error can still be tied to an account.
    scrubbed["user"] = {"id": user["id"]} if user.get("id") else {}
    request = scrubbed.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)
        request["query_string"] = "[redacted]" if request.get("query_string") else ""
    return scrubbed


def scrub_breadcrumb(crumb, hint=None):
    from apps.common.redaction import redact

    return redact(crumb)


def init_sentry(*, environment: str) -> bool:
    """Initialise Sentry if enabled. Returns True if it was initialised."""
    dsn = env_str("SENTRY_DSN", "")
    if not env_bool("SENTRY_ENABLED") or not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=env_str("SENTRY_RELEASE", "") or None,
        integrations=[DjangoIntegration()],
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=scrub_event,
        before_send_transaction=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        traces_sample_rate=env_float("SENTRY_TRACES_SAMPLE_RATE", 0.0),
    )
    return True
