import pytest


@pytest.fixture(autouse=True)
def _fake_sign_in_and_fresh_cache(settings):
    """Tests never call Firebase, Cloud Storage, a KYC provider, a geocoder, WeasyPrint or
    a real e-sign provider, and
    rate-limit counters never leak between tests.

    Deployed settings keep the cache in Postgres; tests use a per-test in-memory one so
    tests without database access can still run.
    """
    from django.core.cache import cache

    from apps.accounts.auth.verifiers import _build
    from apps.agreements import pdf
    from apps.agreements.esign import base as esign
    from apps.geo import geocoders
    from apps.media import storage
    from apps.notifications.channels import base as channels
    from apps.notifications.channels.fake import FakeProvider
    from apps.verification.providers import base as kyc

    settings.AUTH_TOKEN_VERIFIER = "apps.accounts.tests.fakes.FakeTokenVerifier"  # noqa: S105
    settings.MEDIA_STORAGE_CLASS = "apps.media.tests.fakes.InMemoryMediaStorage"
    settings.KYC_PROVIDER = "apps.verification.providers.fake.FakeKycProvider"
    settings.KYC_WEBHOOK_SECRET = "test-kyc-webhook-secret"  # noqa: S105
    settings.GEOCODER = "apps.geo.geocoders.FakeGeocoder"
    settings.AGREEMENT_RENDERER = "apps.agreements.tests.fakes.FakeRenderer"
    settings.ESIGN_PROVIDER = "apps.agreements.esign.fake.FakeESignProvider"
    settings.SCHEDULER_TOKEN_VERIFIER = "apps.bookings.tests.fakes.FakeSchedulerVerifier"  # noqa: S105
    settings.NOTIFICATION_PROVIDERS = {
        "push": "apps.notifications.channels.fake.FakePush",
        "email": "apps.notifications.channels.fake.FakeEmail",
        "sms": "apps.notifications.channels.fake.FakeSms",
        "whatsapp": "apps.notifications.channels.fake.FakeWhatsApp",
    }
    settings.WEB_APP_URL = "https://web.test"
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    }
    cache.clear()  # LocMemCache instances with the same LOCATION share one store
    _build.cache_clear()
    storage._build.cache_clear()  # a fresh, empty fake bucket per test
    kyc._build.cache_clear()  # a fresh fake KYC provider per test
    geocoders._build.cache_clear()
    pdf._build.cache_clear()
    esign._build.cache_clear()  # a fresh fake e-sign provider per test
    channels._build.cache_clear()
    FakeProvider.reset()  # empty fake outboxes per test
    yield
    cache.clear()
    _build.cache_clear()
    storage._build.cache_clear()
    kyc._build.cache_clear()
    geocoders._build.cache_clear()
    pdf._build.cache_clear()
    esign._build.cache_clear()
