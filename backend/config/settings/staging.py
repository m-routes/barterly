"""Staging on Cloud Run. Same as production except a short HSTS max-age."""

from config.sentry import init_sentry
from config.settings.deployed import *  # noqa: F403

# One hour, so a staging domain mistake does not pin browsers for a year.
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_PRELOAD = False
# Preload is deliberately off for staging hostnames.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

SENTRY_ACTIVE = init_sentry(environment="staging")
