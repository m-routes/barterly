"""Helpers for reading configuration from environment variables."""

import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


def env_str(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Environment variable {name} is required")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Environment variable {name} must be an integer") from exc


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Environment variable {name} must be a number") from exc


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def is_unix_socket_host(host: str) -> bool:
    """Cloud SQL on Cloud Run is reached through a socket under /cloudsql/."""
    return host.startswith("/")


def database_config(
    *, ssl_require: bool, pool: bool = False, default_url: str | None = None
) -> dict:
    """Build the default database config from DATABASE_URL.

    Deployed environments use Cloud SQL through Cloud Run's built-in connector: the URL
    host is the percent-encoded socket path, e.g.
    postgres://barterly:PASSWORD@%2Fcloudsql%2FPROJECT%3AREGION%3AINSTANCE/barterly.
    The connector encrypts traffic to the instance and checks IAM, so sslmode is only
    applied to TCP hosts.

    Pooling: under ASGI Django's persistent connections are not reused reliably, so
    deployed settings use Django's psycopg connection pool (one per worker process,
    DB_POOL_MAX_SIZE connections at most) with CONN_MAX_AGE=0. Keep
    instances x workers x DB_POOL_MAX_SIZE below the instance's max_connections.
    """
    url = env_str("DATABASE_URL", default_url)
    config = dj_database_url.parse(
        url,
        conn_max_age=0 if pool else env_int("DB_CONN_MAX_AGE", 0),
        conn_health_checks=not pool,
        ssl_require=False,
    )
    # Retries new connections while the instance restarts (maintenance, failover).
    config["ENGINE"] = "apps.core.db.postgresql"
    options = config.setdefault("OPTIONS", {})
    options.setdefault("connect_timeout", env_int("DB_CONNECT_TIMEOUT", 10))
    if ssl_require and not is_unix_socket_host(str(config.get("HOST", ""))):
        options["sslmode"] = "require"
    if pool:
        options["pool"] = {
            "min_size": env_int("DB_POOL_MIN_SIZE", 1),
            "max_size": env_int("DB_POOL_MAX_SIZE", 4),
            "timeout": env_float("DB_POOL_TIMEOUT", 10.0),
            "max_idle": env_float("DB_POOL_MAX_IDLE", 300.0),
        }
    return config
