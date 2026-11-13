import pytest


@pytest.fixture(autouse=True)
def _fake_sign_in_and_fresh_cache(settings):
    """Tests never call Firebase or Cloud Storage, and rate-limit counters never leak between tests.

    Deployed settings keep the cache in Postgres; tests use a per-test in-memory one so
    tests without database access can still run.
    """
    from django.core.cache import cache

    from apps.accounts.auth.verifiers import _build
    from apps.media import storage

    settings.AUTH_TOKEN_VERIFIER = "apps.accounts.tests.fakes.FakeTokenVerifier"  # noqa: S105
    settings.MEDIA_STORAGE_CLASS = "apps.media.tests.fakes.InMemoryMediaStorage"
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    }
    cache.clear()  # LocMemCache instances with the same LOCATION share one store
    _build.cache_clear()
    storage._build.cache_clear()  # a fresh, empty fake bucket per test
    yield
    cache.clear()
    _build.cache_clear()
    storage._build.cache_clear()
