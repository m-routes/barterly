"""Settings shared by staging and production (Cloud Run + Cloud SQL + Cloud Storage).

Do not point DJANGO_SETTINGS_MODULE here directly; use staging or production.
"""

from config.settings.base import *  # noqa: F403
from config.settings.env import database_config, env_int, env_list, env_str

DEBUG = False

SECRET_KEY = env_str("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list at least one host")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

DATABASES = {"default": database_config(ssl_require=True, pool=True)}

# Google's front end appends the real client IP to X-Forwarded-For; trust only that
# last hop for per-IP rate limits (anything before it is client-supplied).
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": env_int("TRUSTED_PROXY_COUNT", 1)}  # noqa: F405

# Cloud Run terminates TLS and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Cloud Storage: media is private and served only through short-lived signed URLs,
# static files are in a separate public-read bucket.
GS_MEDIA_BUCKET = env_str("GS_MEDIA_BUCKET")
GS_STATIC_BUCKET = env_str("GS_STATIC_BUCKET")
# On Cloud Run there is no private key; sign URLs through the IAM signBlob API
# as the runtime service account (needs roles/iam.serviceAccountTokenCreator on itself).
GS_IAM_SIGN_BLOB = True
GS_SA_EMAIL = env_str("GS_SA_EMAIL", "") or None

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        "OPTIONS": {
            "bucket_name": GS_MEDIA_BUCKET,
            "querystring_auth": True,
            "expiration": env_int("GS_SIGNED_URL_SECONDS", 900),
            "file_overwrite": False,
            "default_acl": None,
        },
    },
    "staticfiles": {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        "OPTIONS": {
            "bucket_name": GS_STATIC_BUCKET,
            "querystring_auth": False,
            "default_acl": None,
            "location": "static",
        },
    },
}
STATIC_URL = f"https://storage.googleapis.com/{GS_STATIC_BUCKET}/static/"


# Health probes come from inside Cloud Run over plain HTTP.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
