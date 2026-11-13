import importlib
from unittest import mock

import pytest
from django.urls import clear_url_caches

from config import sentry


def reload_urls():
    import config.urls

    importlib.reload(config.urls)
    clear_url_caches()


@pytest.fixture
def docs_disabled(settings):
    settings.API_DOCS_ENABLED = False
    reload_urls()
    yield
    settings.API_DOCS_ENABLED = True
    reload_urls()


@pytest.mark.django_db
def test_schema_and_swagger_available_outside_production(client):
    assert client.get("/api/schema/").status_code == 200
    assert client.get("/api/docs/").status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("docs_disabled")
def test_swagger_off_when_disabled_but_schema_stays(client):
    assert client.get("/api/docs/").status_code == 404
    assert client.get("/api/schema/").status_code == 200


class TestSentry:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("SENTRY_ENABLED", raising=False)
        monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/1")
        with mock.patch.object(sentry.sentry_sdk, "init") as init:
            assert sentry.init_sentry(environment="staging") is False
        init.assert_not_called()

    def test_flag_without_dsn_does_nothing(self, monkeypatch):
        monkeypatch.setenv("SENTRY_ENABLED", "1")
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        with mock.patch.object(sentry.sentry_sdk, "init") as init:
            assert sentry.init_sentry(environment="staging") is False
        init.assert_not_called()

    def test_enabled_initialises_without_pii(self, monkeypatch):
        monkeypatch.setenv("SENTRY_ENABLED", "true")
        monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/1")
        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.2")
        monkeypatch.setenv("SENTRY_RELEASE", "ab1357d")
        with mock.patch.object(sentry.sentry_sdk, "init") as init:
            assert sentry.init_sentry(environment="production") is True
        kwargs = init.call_args.kwargs
        assert kwargs["dsn"] == "https://key@o0.ingest.sentry.io/1"
        assert kwargs["environment"] == "production"
        assert kwargs["release"] == "ab1357d"
        assert kwargs["send_default_pii"] is False
        assert kwargs["traces_sample_rate"] == 0.2
