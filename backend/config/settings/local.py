"""Local development and tests. Never used in a deployed environment."""

from apps.common.logging import logging_config
from config.settings.base import *  # noqa: F403
from config.settings.env import database_config, env_bool, env_list, env_str

DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = env_str("DJANGO_SECRET_KEY", "insecure-local-only-key-never-use-when-deployed")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")

DATABASES = {
    "default": database_config(
        ssl_require=False,
        default_url="postgres://barterly:barterly@localhost:5432/barterly",
    )
}

LOGGING = logging_config(
    fmt=env_str("LOG_FORMAT", "plain"),
    level=env_str("DJANGO_LOG_LEVEL", "INFO"),
)

# Local development checks nothing: finish ID checks with `manage.py fake_kyc_result`.
KYC_PROVIDER = "apps.verification.providers.fake.FakeKycProvider"
KYC_WEBHOOK_SECRET = env_str("KYC_WEBHOOK_SECRET", "local-only-fake-kyc-webhook-secret")
