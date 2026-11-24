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

# The acceptance suite's local stack (docs/qa/README.md): every outside service is a
# stand-in, so the journeys run on a laptop or a CI runner with no accounts anywhere.
# Sign-in accepts `fake-otp:<phone>` tokens (the web's local fake sign-in makes them).
# Only this local settings module reads the switch; deployed settings never do.
if env_bool("LOCAL_ACCEPTANCE_STACK", False):
    AUTH_TOKEN_VERIFIER = "apps.accounts.tests.fakes.FakeTokenVerifier"  # nosec B105  # noqa: S105
    MEDIA_STORAGE_CLASS = "apps.media.tests.fakes.InMemoryMediaStorage"
    ESCROW_GATEWAY = "apps.money.gateway.fake.FakeEscrowGateway"
    PAYOUT_PROVIDER = "apps.money.gateway.fake.FakePayoutProvider"
    BILLING_GATEWAY = "apps.billing.gateway.fake.FakeGateway"
    NOTIFICATION_PROVIDERS = {
        **NOTIFICATION_PROVIDERS,  # noqa: F405
        "push": "apps.notifications.channels.fake.FakePush",
    }
    GEOCODER = "apps.geo.geocoders.FakeGeocoder"
