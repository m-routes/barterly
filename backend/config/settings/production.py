"""Production on Cloud Run."""

from config.sentry import init_sentry
from config.settings.deployed import *  # noqa: F403

SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_PRELOAD = True

# Interactive docs are for development and staging only.
API_DOCS_ENABLED = False

SENTRY_ACTIVE = init_sentry(environment="production")
