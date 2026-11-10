"""Tests for settings helpers and the deployed settings modules."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import env

BACKEND_DIR = Path(__file__).resolve().parents[3]

SOCKET = "/cloudsql/proj-1:asia-south1:barterly-staging"
CLOUD_SQL_URL = "postgres://u:p@%2Fcloudsql%2Fproj-1%3Aasia-south1%3Abarterly-staging/barterly"
TCP_URL = "postgres://u:p@db.example.test:5432/barterly"


def test_env_helpers(monkeypatch):
    monkeypatch.setenv("X_INT", "7")
    monkeypatch.setenv("X_FLOAT", "0.25")
    monkeypatch.setenv("X_BOOL", "Yes")
    monkeypatch.setenv("X_LIST", "a.com, b.com,,")
    assert env.env_int("X_INT", 1) == 7
    assert env.env_int("X_MISSING", 3) == 3
    assert env.env_float("X_FLOAT", 1.0) == 0.25
    assert env.env_float("X_MISSING", 1.5) == 1.5
    assert env.env_bool("X_BOOL") is True
    assert env.env_list("X_LIST") == ["a.com", "b.com"]


@pytest.mark.parametrize("fn", [env.env_int, env.env_float])
def test_numeric_env_rejects_garbage(monkeypatch, fn):
    monkeypatch.setenv("X_BAD", "abc")
    with pytest.raises(ImproperlyConfigured):
        fn("X_BAD", 1)


def test_env_str_required(monkeypatch):
    monkeypatch.delenv("X_REQUIRED", raising=False)
    with pytest.raises(ImproperlyConfigured, match="X_REQUIRED"):
        env.env_str("X_REQUIRED")


def test_unix_socket_detection():
    assert env.is_unix_socket_host(SOCKET)
    assert not env.is_unix_socket_host("db.example.test")
    assert not env.is_unix_socket_host("")


def test_database_config_for_cloud_sql_socket_with_pool(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", CLOUD_SQL_URL)
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "3")
    monkeypatch.setenv("DB_CONN_MAX_AGE", "60")  # ignored: pooling needs CONN_MAX_AGE=0
    cfg = env.database_config(ssl_require=True, pool=True)
    assert cfg["ENGINE"] == "apps.core.db.postgresql"
    assert cfg["HOST"] == SOCKET
    assert cfg["NAME"] == "barterly"
    assert cfg["CONN_MAX_AGE"] == 0
    assert cfg["CONN_HEALTH_CHECKS"] is False
    assert "sslmode" not in cfg["OPTIONS"]  # the connector encrypts the socket traffic
    assert cfg["OPTIONS"]["connect_timeout"] == 10
    assert cfg["OPTIONS"]["pool"] == {
        "min_size": 1,
        "max_size": 3,
        "timeout": 10.0,
        "max_idle": 300.0,
    }


def test_database_config_tcp_requires_ssl(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TCP_URL)
    monkeypatch.delenv("DB_CONN_MAX_AGE", raising=False)
    cfg = env.database_config(ssl_require=True)
    assert cfg["OPTIONS"]["sslmode"] == "require"
    assert cfg["CONN_MAX_AGE"] == 0
    assert cfg["CONN_HEALTH_CHECKS"] is True
    assert "pool" not in cfg["OPTIONS"]


def test_database_config_local_tuning(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TCP_URL)
    monkeypatch.setenv("DB_CONN_MAX_AGE", "60")
    cfg = env.database_config(ssl_require=False)
    assert cfg["CONN_MAX_AGE"] == 60
    assert "sslmode" not in cfg["OPTIONS"]


def deployed_env(**overrides: str) -> dict[str, str]:
    base = {
        "PATH": os.environ["PATH"],
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_ALLOWED_HOSTS": "api.example.test",
        "DATABASE_URL": CLOUD_SQL_URL,
        "GS_MEDIA_BUCKET": "media-bucket",
        "GS_STATIC_BUCKET": "static-bucket",
    }
    base.update(overrides)
    return base


def run_manage(settings_module: str, *args: str, env_vars: dict[str, str]):
    return subprocess.run(  # noqa: S603 - fixed argv, test only
        [sys.executable, "manage.py", *args],
        cwd=BACKEND_DIR,
        env={**env_vars, "DJANGO_SETTINGS_MODULE": settings_module},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("module", ["config.settings.staging", "config.settings.production"])
def test_deployed_settings_pass_deploy_checks(module):
    result = run_manage(
        module, "check", "--deploy", "--fail-level", "WARNING", env_vars=deployed_env()
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("missing", ["DJANGO_SECRET_KEY", "DATABASE_URL", "GS_MEDIA_BUCKET"])
def test_production_refuses_to_start_without_required_env(missing):
    env_vars = deployed_env()
    del env_vars[missing]
    result = run_manage("config.settings.production", "check", env_vars=env_vars)
    assert result.returncode != 0
    assert missing in result.stderr


def test_production_requires_allowed_hosts():
    result = run_manage(
        "config.settings.production", "check", env_vars=deployed_env(DJANGO_ALLOWED_HOSTS="")
    )
    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_production_security_settings():
    code = (
        "from django.conf import settings as s;"
        "print(s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT,"
        " s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_PRELOAD,"
        " s.STORAGES['default']['OPTIONS']['querystring_auth'])"
    )
    result = run_manage("config.settings.production", "shell", "-c", code, env_vars=deployed_env())
    assert result.returncode == 0, result.stderr
    values = result.stdout.strip().splitlines()[-1].split()
    assert values == ["False", "True", "True", "True", "31536000", "True", "True"]
