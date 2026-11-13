"""Optional Sentry error reporting.

Enabled only when SENTRY_ENABLED is truthy and SENTRY_DSN is set. The DSN belongs in
Secret Manager, never in code. PII is not sent (phone numbers are user identifiers).
"""

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from config.settings.env import env_bool, env_float, env_str


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
        traces_sample_rate=env_float("SENTRY_TRACES_SAMPLE_RATE", 0.0),
    )
    return True
