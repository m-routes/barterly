"""Settings shared by every environment. Environment modules import from here."""

from datetime import timedelta
from pathlib import Path

from apps.common.logging import logging_config
from config.settings.env import env_bool, env_float, env_int, env_str

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "apps.backoffice.apps.BarterlyAdminConfig",  # django.contrib.admin, Barterly site
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "apps.core",
    "apps.common",
    "apps.accounts",
    "apps.profiles",
    "apps.media",
    "apps.geo",
    "apps.properties",
    "apps.verification",
    "apps.gigs",
    "apps.discovery",
    "apps.notifications",
    "apps.applications",
    "apps.backoffice.apps.BackofficeConfig",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "apps.common.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Connection retry while the database restarts (see apps.core.db.postgresql).
DB_CONNECT_ATTEMPTS = env_int("DB_CONNECT_ATTEMPTS", 4)
DB_CONNECT_RETRY_DELAY = env_float("DB_CONNECT_RETRY_DELAY", 0.5)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Apps send the JWT from /api/v1/auth/exchange/; the session is for the Django admin.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.common.exceptions.exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "auth_exchange_ip": env_str("THROTTLE_AUTH_EXCHANGE_IP", "60/hour"),
        "auth_exchange_phone": env_str("THROTTLE_AUTH_EXCHANGE_PHONE", "10/hour"),
        "media_upload": env_str("THROTTLE_MEDIA_UPLOAD", "120/hour"),
        "kyc_start": env_str("THROTTLE_KYC_START", "5/day"),
        "geocode": env_str("THROTTLE_GEOCODE", "30/hour"),
        "property_public": env_str("THROTTLE_PROPERTY_PUBLIC", "600/hour"),
    },
    # Proxies in front of Django that append to X-Forwarded-For. 0 = use REMOTE_ADDR.
    "NUM_PROXIES": env_int("TRUSTED_PROXY_COUNT", 0),
}

# Throttle counters must be shared by every instance, so they live in Postgres
# (`manage.py createcachetable`, run by the release command).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 30)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,  # the exchange view records it
    "ALGORITHM": "HS256",  # signed with SECRET_KEY, which comes from Secret Manager
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Sign-in token verifier (see apps.accounts.auth.verifiers). Set in code, not from the
# environment, so a deployed service can't be pointed at the test fake.
AUTH_TOKEN_VERIFIER = "apps.accounts.auth.verifiers.FirebaseTokenVerifier"  # noqa: S105 (class path)
FIREBASE_PROJECT_ID = env_str("FIREBASE_PROJECT_ID", "")
FIREBASE_CHECK_REVOKED = env_bool("FIREBASE_CHECK_REVOKED", False)

# Swagger UI at /api/docs/. Turned off in production; the schema stays at /api/schema/.
API_DOCS_ENABLED = env_bool("API_DOCS_ENABLED", True)

SPECTACULAR_SETTINGS = {
    "TITLE": "Barterly API",
    "DESCRIPTION": "Work-exchange marketplace for travel and hospitality in India.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Stable names where two apps use the same field name (status, kind, ...).
    "ENUM_NAME_OVERRIDES": {
        "VerificationStatusEnum": "apps.verification.constants.CaseStatus",
        "VerificationDocumentStatusEnum": "apps.verification.constants.DocumentStatus",
        "VerificationDocumentTypeEnum": "apps.verification.constants.DocumentType",
        "IdDocumentTypeEnum": "apps.verification.constants.ID_DOCUMENT_CHOICES",
        "BadgeKindEnum": "apps.verification.constants.BadgeKind",
        "KindEnum": "apps.media.policy.Kind",
        "GigStatusEnum": "apps.gigs.constants.GigStatus",
        "DeliverableTypeEnum": "apps.gigs.constants.DeliverableType",
        "ApplicationStatusEnum": "apps.applications.constants.ApplicationStatus",
        "AttachmentKindEnum": "apps.applications.models.AttachmentKind",
    },
}

# Structured JSON logs (one object per line, with request_id). LOG_FORMAT=plain for
# human-readable local output.
LOGGING = logging_config(
    fmt=env_str("LOG_FORMAT", "json"),
    level=env_str("DJANGO_LOG_LEVEL", "INFO"),
)

# Uploads (apps.media). Files live in the private media bucket and are only ever reached
# through short-lived signed URLs. Class paths are code settings, like the verifier.
MEDIA_BUCKET = env_str("GS_MEDIA_BUCKET", "")
GS_SA_EMAIL = env_str("GS_SA_EMAIL", "") or None
MEDIA_STORAGE_CLASS = "apps.media.storage.GCSMediaStorage"
MEDIA_VIRUS_SCANNER = "apps.media.scanning.NoopVirusScanner"
TASK_QUEUE_CLASS = "apps.media.tasks.InlineTaskQueue"
MEDIA_UPLOAD_URL_SECONDS = env_int("MEDIA_UPLOAD_URL_SECONDS", 900)
MEDIA_READ_URL_SECONDS = env_int("MEDIA_READ_URL_SECONDS", 300)
MEDIA_MAX_PENDING_UPLOADS = env_int("MEDIA_MAX_PENDING_UPLOADS", 20)
# Serve only files a virus scanner passed. Off until a real scanner is wired up.
MEDIA_REQUIRE_SCAN = env_bool("MEDIA_REQUIRE_SCAN", False)

# Verification (apps.verification). The KYC provider is a code setting like the token
# verifier: deployed services use the real provider (a stub until one is chosen, which
# answers 503), never the fake. The webhook secret comes from Secret Manager.
KYC_PROVIDER = "apps.verification.providers.external.ExternalKycProvider"
KYC_WEBHOOK_SECRET = env_str("KYC_WEBHOOK_SECRET", "")
VERIFICATION_MIN_PROPERTY_PHOTOS = env_int("VERIFICATION_MIN_PROPERTY_PHOTOS", 3)
VERIFICATION_PHOTO_MAX_DISTANCE_M = env_int("VERIFICATION_PHOTO_MAX_DISTANCE_M", 500)

# Geocoding (apps.geo). Nominatim's usage policy: identify the app, at most one request
# per second (enforced across instances through the shared cache), cache every answer.
GEOCODER = "apps.geo.geocoders.NominatimGeocoder"
NOMINATIM_URL = env_str("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
NOMINATIM_USER_AGENT = env_str(
    "NOMINATIM_USER_AGENT", "Barterly/0.1 (+https://github.com/m-routes/barterly)"
)
NOMINATIM_EMAIL = env_str("NOMINATIM_EMAIL", "")
GEOCODER_TIMEOUT_SECONDS = env_int("GEOCODER_TIMEOUT_SECONDS", 5)

# Gigs (apps.gigs): how many live gigs a vendor's plan allows. Unlimited for now.
GIG_PLAN_POLICY = "apps.gigs.plans.UnlimitedPlanPolicy"

# Discovery (apps.discovery). Fit-score weights: they needn't add to 100 (they are
# scaled), but keeping them at 100 makes each one read as "points".
DISCOVERY_FIT_WEIGHTS = {
    "skill_match": 30,
    "reliability": 25,
    "ratings": 20,
    "audience_quality": 15,
    "distance_availability": 10,
}
DISCOVERY_DISTANCE_ZERO_KM = env_int("DISCOVERY_DISTANCE_ZERO_KM", 300)
DISCOVERY_PAGE_SIZE = env_int("DISCOVERY_PAGE_SIZE", 20)
# best_fit scores the newest matching gigs in Python; this caps how many.
DISCOVERY_MAX_CANDIDATES = env_int("DISCOVERY_MAX_CANDIDATES", 1000)
