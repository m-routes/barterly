"""Local development and tests. Never used in a deployed environment."""

from config.settings.base import *  # noqa: F403
from config.settings.env import database_config, env_bool, env_list, env_str

DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = env_str("DJANGO_SECRET_KEY", "insecure-local-only-key")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")

DATABASES = {
    "default": database_config(
        ssl_require=False,
        default_url="postgres://barterly:barterly@localhost:5432/barterly",
    )
}
