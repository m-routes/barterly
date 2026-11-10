"""Production on Cloud Run."""

from config.settings.deployed import *  # noqa: F403

SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_PRELOAD = True
