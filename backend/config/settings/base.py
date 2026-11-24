"""Settings shared by every environment. Environment modules import from here."""

from datetime import timedelta
from pathlib import Path

from apps.common.logging import logging_config
from config.settings.env import env_bool, env_float, env_int, env_list, env_str

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
    "apps.bookings",
    "apps.hiring",
    "apps.chat",
    "apps.offers",
    "apps.agreements",
    "apps.reliability",
    "apps.billing",
    "apps.money",
    "apps.attendance",
    "apps.deliverables",
    "apps.reviews",
    "apps.flags",
    "apps.privacy",
    "apps.backoffice.apps.BackofficeConfig",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "apps.common.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.SecurityHeadersMiddleware",
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

# --- Request limits (ASVS 13.1 / 12.1): reject oversized bodies before parsing.
# JSON bodies are small; files go straight to Cloud Storage via signed URLs.
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 1024 * 1024)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 500
DATA_UPLOAD_MAX_NUMBER_FILES = 5
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
# Cross-Origin-Opener-Policy (Django's default, stated for the record).
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
# The API is called same-origin by the web BFF and natively by the app: no CORS.
# Origins allowed to show admin images (e.g. the media bucket), for the admin CSP.
CSP_MEDIA_ORIGINS = ["https://storage.googleapis.com"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "apps.common.schema.BarterlyAutoSchema",
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
        "chat_send": env_str("THROTTLE_CHAT_SEND", "30/minute"),
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
AUTH_TOKEN_VERIFIER = "apps.accounts.auth.verifiers.FirebaseTokenVerifier"  # nosec B105  # noqa: S105 (class path)
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
        "ConsentPurposeEnum": "apps.privacy.models.Purpose",
        "ConsentSourceEnum": "apps.privacy.models.CLIENT_SOURCES",
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
        "BookingStatusEnum": "apps.bookings.lifecycle.BookingStatus",
        "BookingActorEnum": "apps.bookings.lifecycle.Actor",
        "SubscriptionStatusEnum": "apps.billing.models.SubscriptionStatus",
        "EscrowDecisionEnum": "apps.money.escrow.DECISIONS",
        "DecisionEnum": "apps.verification.services.cases.Decision.CHOICES",
        "SubmissionReviewEnum": "apps.money.models.SubmissionReview",
        "PayoutMethodEnum": "apps.money.models.PayoutMethod",
        # The agreements signing method (otp/none), named before payouts added a "method".
        "MethodEnum": "apps.agreements.serializers.CHALLENGE_METHODS",
        "PayoutValidationStatusEnum": "apps.money.models.ValidationStatus",
        "PayoutAttemptStatusEnum": "apps.money.models.PayoutAttemptStatus",
        "PayoutTriggerEnum": "apps.money.models.PayoutTrigger",
        "CheckInMethodEnum": "apps.attendance.models.CheckInMethod",
        "HourStatusEnum": "apps.attendance.models.HourStatus",
        "DeliverableKindEnum": "apps.deliverables.models.Kind",
        "DeliverablePlatformEnum": "apps.deliverables.models.Platform",
        "DeliverableStatusEnum": "apps.deliverables.models.Status",
        "PostStatsSourceEnum": "apps.deliverables.models.StatsSource",
        "ReviewSideEnum": "apps.reviews.models.Side",
        "ReviewStatusEnum": "apps.reviews.models.ReviewStatus",
        "ReportReasonEnum": "apps.reviews.models.ReportReason",
        "CancellationReasonEnum": "apps.bookings.models.CancellationReason",
        "CancellationEffectEnum": "apps.bookings.models.CancellationEffect",
        "CancelledByEnum": "apps.bookings.models.CancelledBy",
        "ReliabilitySideEnum": "apps.reliability.models.Side",
        "NotificationChannelEnum": "apps.notifications.models.Channel",
        "NotificationLocaleEnum": "apps.notifications.models.Locale",
        "DevicePlatformEnum": "apps.notifications.models.DevicePlatform",
        "VendorApplicationMoveEnum": ["shortlisted", "interview", "offered", "rejected"],
        "RejectionReasonEnum": ["not_a_fit", "dates", "filled", "language", "incomplete", "other"],
        "InterviewStatusEnum": "apps.hiring.models.InterviewStatus",
        "ChatReportReasonEnum": "apps.chat.models.ReportReason",
        "PartyEnum": "apps.offers.models.Party",
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
# Background tasks (apps/media/tasks.py). Deployed: Cloud Tasks, calling
# POST /api/v1/tasks/<name>/ with an OIDC token for the tasks service account.
TASK_QUEUE_CLASS = env_str("TASK_QUEUE_CLASS", "apps.media.tasks.InlineTaskQueue")
CLOUD_TASKS_PROJECT = env_str("CLOUD_TASKS_PROJECT", "")
CLOUD_TASKS_LOCATION = env_str("CLOUD_TASKS_LOCATION", "asia-south1")
CLOUD_TASKS_QUEUE = env_str("CLOUD_TASKS_QUEUE", "")
TASKS_AUDIENCE = env_str("TASKS_AUDIENCE", "")
TASKS_INVOKER_EMAIL = env_str("TASKS_INVOKER_EMAIL", "")
MEDIA_UPLOAD_URL_SECONDS = env_int("MEDIA_UPLOAD_URL_SECONDS", 900)
MEDIA_READ_URL_SECONDS = env_int("MEDIA_READ_URL_SECONDS", 300)
MEDIA_MAX_PENDING_UPLOADS = env_int("MEDIA_MAX_PENDING_UPLOADS", 20)
# Serve only files a virus scanner passed. Off until a real scanner is wired up.
MEDIA_REQUIRE_SCAN = env_bool("MEDIA_REQUIRE_SCAN", False)
# ClamAV (apps.media.scanning.ClamdVirusScanner). Setting CLAMAV_HOST (the sidecar is
# localhost) switches scanning on and, unless overridden, requires it.
CLAMAV_HOST = env_str("CLAMAV_HOST", "")
CLAMAV_PORT = env_int("CLAMAV_PORT", 3310)
CLAMAV_TIMEOUT_SECONDS = env_int("CLAMAV_TIMEOUT_SECONDS", 60)
if CLAMAV_HOST:
    MEDIA_VIRUS_SCANNER = "apps.media.scanning.ClamdVirusScanner"
    MEDIA_REQUIRE_SCAN = env_bool("MEDIA_REQUIRE_SCAN", True)
# Signed links stay short-lived (ASVS 12.5); test_signed_url_lifetimes holds the cap.
MEDIA_MAX_SIGNED_URL_SECONDS = 900

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
# How many live gigs a vendor may have: their billing plan (apps.billing.entitlements).
GIG_PLAN_POLICY = "apps.billing.entitlements.BillingPlanPolicy"

# Billing (apps.billing). Razorpay Subscriptions; keys from Secret Manager.
BILLING_GATEWAY = env_str("BILLING_GATEWAY", "apps.billing.gateway.razorpay.RazorpayGateway")
RAZORPAY_KEY_ID = env_str("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = env_str("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = env_str("RAZORPAY_WEBHOOK_SECRET", "")
# Days of free trial for a vendor's first subscription (the launch cohort); 0 is off.
# Coupons give their own trial either way.
BILLING_LAUNCH_TRIAL_DAYS = env_int("BILLING_LAUNCH_TRIAL_DAYS", 0)
# After a failed charge, paid features stay on this long while the gateway retries.
BILLING_GRACE_DAYS = env_int("BILLING_GRACE_DAYS", 7)
BILLING_GST_RATE = env_float("BILLING_GST_RATE", 18.0)
BILLING_INVOICE_PREFIX = env_str("BILLING_INVOICE_PREFIX", "BRT")
# The supplier on every invoice. Fill in the registered details before launch.
BILLING_SUPPLIER = {
    "legal_name": env_str("BILLING_SUPPLIER_NAME", "[Legal name] Pvt Ltd"),
    "gstin": env_str("BILLING_SUPPLIER_GSTIN", "[GSTIN]"),
    "address": env_str("BILLING_SUPPLIER_ADDRESS", "[Registered address]"),
    "state": env_str("BILLING_SUPPLIER_STATE", "Karnataka"),
    "email": env_str("BILLING_SUPPLIER_EMAIL", "billing@barterly.in"),
}

# Money (apps.money): the ledger and escrow for paid and hybrid bookings.
# LEGAL REVIEW NEEDED: the fund-flow structure behind ESCROW_GATEWAY.
# CA REVIEW NEEDED: every rate and threshold below. Rates are basis points (800 = 8%).
ESCROW_GATEWAY = env_str("ESCROW_GATEWAY", "apps.money.gateway.razorpay.RazorpayEscrowGateway")
RAZORPAY_ESCROW_WEBHOOK_SECRET = env_str("RAZORPAY_ESCROW_WEBHOOK_SECRET", "")
ESCROW_COMMISSION_BPS = env_int("ESCROW_COMMISSION_BPS", 800)
ESCROW_GST_BPS = env_int("ESCROW_GST_BPS", 1800)  # on the commission and the fee recovery
ESCROW_GATEWAY_FEE_BPS = env_int("ESCROW_GATEWAY_FEE_BPS", 200)  # charged to the host
ESCROW_TDS_ENABLED = env_bool("ESCROW_TDS_ENABLED", True)
ESCROW_TDS_BPS = env_int("ESCROW_TDS_BPS", 100)  # with PAN
ESCROW_TDS_NO_PAN_BPS = env_int("ESCROW_TDS_NO_PAN_BPS", 2000)
ESCROW_TDS_THRESHOLD_PAISE = env_int("ESCROW_TDS_THRESHOLD_PAISE", 0)  # per release
ESCROW_AUTO_RELEASE_HOURS = env_int("ESCROW_AUTO_RELEASE_HOURS", 72)
# The kill switch (also in admin, Money > Escrow control): no new funding or payouts.
ESCROW_PAUSED = env_bool("ESCROW_PAUSED", False)
ESCROW_ALERT_EMAILS = env_list("ESCROW_ALERT_EMAILS", "")
# TDS records (apps.money.wallet). CA REVIEW NEEDED: the section and the rates above.
ESCROW_TDS_SECTION = env_str("ESCROW_TDS_SECTION", "194-O")
ESCROW_TDS_TAN = env_str("ESCROW_TDS_TAN", "[TAN]")

# Payouts to talent (apps.money.payouts): RazorpayX fund accounts and payouts.
# LEGAL REVIEW NEEDED: funding the RazorpayX account from the gateway settlement.
PAYOUT_PROVIDER = env_str("PAYOUT_PROVIDER", "apps.money.gateway.payouts.RazorpayXProvider")
RAZORPAYX_ACCOUNT_NUMBER = env_str("RAZORPAYX_ACCOUNT_NUMBER", "")
RAZORPAYX_WEBHOOK_SECRET = env_str("RAZORPAYX_WEBHOOK_SECRET", "")
PAYOUT_ACCOUNT_CHANGE_HOLD_HOURS = env_int("PAYOUT_ACCOUNT_CHANGE_HOLD_HOURS", 24)
PAYOUT_MAX_ATTEMPTS = env_int("PAYOUT_MAX_ATTEMPTS", 5)
PAYOUT_RUN_LIMIT = env_int("PAYOUT_RUN_LIMIT", 500)
PAYOUT_ON_DEMAND_EVERY_MINUTES = env_int("PAYOUT_ON_DEMAND_EVERY_MINUTES", 10)

# Attendance (apps.attendance): signed check-in passes, codes, hours.
# The Ed25519 private key: 32 random bytes, base64 (Secret Manager in deployed
# environments; local runs derive one from SECRET_KEY). Rotate by moving the old public
# key into ATTENDANCE_PREVIOUS_PUBLIC_KEYS for a day.
ATTENDANCE_SIGNING_KEY = env_str("ATTENDANCE_SIGNING_KEY", "")
# Field-level encryption (apps.common.encryption): "id:base64(32 bytes)" pairs, comma
# separated, newest first. Secret Manager when deployed; local runs derive a key.
FIELD_ENCRYPTION_KEYS = env_str("FIELD_ENCRYPTION_KEYS", "")

# Feature flags (apps.flags): how long instances cache them, so a change made in the
# back office reaches every instance within this many seconds.
FLAG_CACHE_SECONDS = env_int("FLAG_CACHE_SECONDS", 30)
ATTENDANCE_PREVIOUS_PUBLIC_KEYS = env_list("ATTENDANCE_PREVIOUS_PUBLIC_KEYS", "")
ATTENDANCE_PASS_HOURS = env_int("ATTENDANCE_PASS_HOURS", 48)
ATTENDANCE_GEOFENCE_FLAG_METERS = env_int("ATTENDANCE_GEOFENCE_FLAG_METERS", 1000)
ATTENDANCE_SYNC_MAX_AGE_HOURS = env_int("ATTENDANCE_SYNC_MAX_AGE_HOURS", 72)
ATTENDANCE_CLOCK_SKEW_SECONDS = env_int("ATTENDANCE_CLOCK_SKEW_SECONDS", 120)
ATTENDANCE_NO_SHOW_GRACE_HOURS = env_int("ATTENDANCE_NO_SHOW_GRACE_HOURS", 18)

# Deliverables (apps.deliverables): post stats from the platforms, behind
# SOCIAL_STATS_PROVIDER. YouTube: a Data API key. Instagram: the Graph API's business
# discovery through Barterly's own business account. META APP REVIEW NEEDED before
# INSTAGRAM_STATS_ENABLED; until then talent enter numbers by hand (self-reported).
SOCIAL_STATS_PROVIDER = env_str(
    "SOCIAL_STATS_PROVIDER", "apps.deliverables.stats.base.CombinedProvider"
)
SOCIAL_STATS_PROVIDERS = [
    "apps.deliverables.stats.providers.YouTubeProvider",
    "apps.deliverables.stats.providers.InstagramProvider",
]
YOUTUBE_API_KEY = env_str("YOUTUBE_API_KEY", "")
INSTAGRAM_STATS_ENABLED = env_bool("INSTAGRAM_STATS_ENABLED", False)
INSTAGRAM_GRAPH_TOKEN = env_str("INSTAGRAM_GRAPH_TOKEN", "")
INSTAGRAM_BUSINESS_ACCOUNT_ID = env_str("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

# Reviews and reputation (apps.reviews).
REVIEW_WINDOW_DAYS = env_int("REVIEW_WINDOW_DAYS", 14)
REVIEW_MIN_LENGTH = env_int("REVIEW_MIN_LENGTH", 20)
# Words that hold a review or reply for a moderator: accusations to check, and moves
# off the platform. Phone numbers, emails and links are held as well (moderation.py).
REVIEW_FLAGGED_WORDS = env_list(
    "REVIEW_FLAGGED_WORDS", "scam,fraud,cheat,harass,whatsapp,telegram,gpay,paytm,phonepe"
)
# Badges, as data (apps.reviews.badges checks them at startup). Each condition is a
# metric with a min and/or max; every condition must hold.
TRUSTED_MEMBER_CLEAN_GIGS = env_int("TRUSTED_MEMBER_CLEAN_GIGS", 5)
REPUTATION_BADGES = [
    {
        "key": "verified_creator",
        "label": "Verified Creator",
        "side": "talent",
        "all": [
            {"metric": "id_verified", "min": 1},
            {"metric": "instagram_linked", "min": 1},
            {"metric": "completed_content_gigs", "min": 1},
            {"metric": "rating_average", "min": 4.0},
        ],
    },
    {
        "key": "top_volunteer",
        "label": "Top Volunteer",
        "side": "talent",
        "all": [
            {"metric": "completed_volunteer_gigs", "min": 3},
            {"metric": "rating_average", "min": 4.5},
            {"metric": "no_shows", "max": 0},
        ],
    },
    {
        "key": "trusted_member",
        "label": "Trusted member",
        "side": "any",
        "all": [
            {"metric": "clean_gigs", "min": TRUSTED_MEMBER_CLEAN_GIGS},
            {"metric": "no_shows", "max": 0},
            {"metric": "late_cancellations", "max": 0},
        ],
    },
]

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

# Scheduled jobs: Cloud Scheduler calls POST /api/v1/jobs/<name>/ with an OIDC token for
# the scheduler service account (apps/bookings/scheduler.py). Terraform sets both values.
SCHEDULER_TOKEN_VERIFIER = "apps.bookings.scheduler.GoogleOidcVerifier"  # nosec B105  # noqa: S105 (a class path)
SCHEDULER_AUDIENCE = env_str("SCHEDULER_AUDIENCE", "")
SCHEDULER_INVOKER_EMAIL = env_str("SCHEDULER_INVOKER_EMAIL", "")

# Notifications (apps.notifications). One provider per channel; None switches the
# channel off. SMS and WhatsApp wait for a provider choice (MSG91, Gupshup, Twilio, ...):
# write it against apps.notifications.channels.base.ChannelProvider.
NOTIFICATION_PROVIDERS = {
    "push": env_str("NOTIFY_PUSH_PROVIDER", "apps.notifications.channels.fcm.FcmPushProvider")
    or None,
    "email": env_str(
        "NOTIFY_EMAIL_PROVIDER", "apps.notifications.channels.email.DjangoEmailProvider"
    )
    or None,
    "sms": env_str("NOTIFY_SMS_PROVIDER", "") or None,
    "whatsapp": env_str("NOTIFY_WHATSAPP_PROVIDER", "") or None,
}
# Attempts before a delivery is a dead letter. Keep at or below the Cloud Tasks queue's
# max_attempts (infra/terraform/modules/environment/tasks.tf).
NOTIFICATION_MAX_ATTEMPTS = env_int("NOTIFICATION_MAX_ATTEMPTS", 6)
# The web console, for links in emails, SMS and web push.
WEB_APP_URL = env_str("WEB_APP_URL", "http://localhost:3000")
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "Barterly <notifications@barterly.in>")
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = 10

# Chat (apps.chat). The profanity filter is a hook like the other provider settings:
# the default lets everything through; WordListProfanityFilter masks the listed words.
CHAT_PROFANITY_FILTER = "apps.chat.filters.NoopProfanityFilter"
CHAT_PROFANITY_WORDS = env_list("CHAT_PROFANITY_WORDS")

# Agreements (apps.agreements). Code settings, like KYC_PROVIDER: a deployed service
# can't be pointed at a fake from the environment.
AGREEMENT_RENDERER = "apps.agreements.pdf.WeasyPrintRenderer"
ESIGN_PROVIDER = "apps.agreements.esign.inapp.InAppESignProvider"
# When both sides sign and the gig's slots are full, other open offers and unsigned
# bookings for it are put on "hold" (until a place opens) or "expire"d.
BOOKING_WHEN_FULL = env_str("BOOKING_WHEN_FULL", "hold")
# When a confirmed booking is cancelled and nobody is in line, offer the place to the
# next shortlisted applicant on the same terms.
STEP_IN_OFFERS = env_bool("STEP_IN_OFFERS", True)

# Privacy (apps.privacy, docs/privacy.md). LEGAL REVIEW NEEDED: every value below.
# The version of each document people consent to. Bump one when its text changes; people
# are asked again, and the consent record says which version they agreed to.
PRIVACY_DOCUMENT_VERSIONS = {
    "terms": env_str("PRIVACY_TERMS_VERSION", "2026-11-draft-1"),
    "privacy": env_str("PRIVACY_POLICY_VERSION", "2026-11-draft-1"),
    "location": env_str("PRIVACY_LOCATION_VERSION", "2026-11-draft-1"),
    "social": env_str("PRIVACY_SOCIAL_VERSION", "2026-11-draft-1"),
    "marketing": env_str("PRIVACY_MARKETING_VERSION", "2026-11-draft-1"),
}
# How long each kind of data is kept, in days (apps.privacy.retention, run daily by the
# privacy_retention job). Each purge writes an audit entry.
PRIVACY_RETENTION_DAYS = {
    "notifications": env_int("RETAIN_NOTIFICATIONS_DAYS", 180),
    "push_devices": env_int("RETAIN_PUSH_DEVICES_DAYS", 270),
    "chat_leakage_bodies": env_int("RETAIN_CHAT_LEAKAGE_DAYS", 90),
    "gateway_payloads": env_int("RETAIN_GATEWAY_PAYLOADS_DAYS", 180),
    "attendance_locations": env_int("RETAIN_ATTENDANCE_LOCATIONS_DAYS", 30),
    "verification_references": env_int("RETAIN_VERIFICATION_REFERENCES_DAYS", 365),
    "job_runs": env_int("RETAIN_JOB_RUNS_DAYS", 90),
}
# Exports: the file is kept this long, and each download link lasts this many seconds.
PRIVACY_EXPORT_KEEP_HOURS = env_int("PRIVACY_EXPORT_KEEP_HOURS", 24)
PRIVACY_EXPORT_URL_SECONDS = env_int("PRIVACY_EXPORT_URL_SECONDS", 300)
PRIVACY_EXPORTS_PER_DAY = env_int("PRIVACY_EXPORTS_PER_DAY", 3)
# A deletion request waits this long (it can be cancelled) before the account is
# anonymised by the privacy_deletions job.
PRIVACY_DELETION_GRACE_DAYS = env_int("PRIVACY_DELETION_GRACE_DAYS", 7)
# The Grievance Officer (IT Rules 2021, rule 3(2); DPDP Act s.8(10)). Shown on the public
# grievance page. LEGAL REVIEW NEEDED: name and contact before launch.
GRIEVANCE_OFFICER = {
    "name": env_str("GRIEVANCE_OFFICER_NAME", "[Grievance Officer name]"),
    "email": env_str("GRIEVANCE_OFFICER_EMAIL", "grievance@barterly.in"),
    "phone": env_str("GRIEVANCE_OFFICER_PHONE", ""),
    "address": env_str("GRIEVANCE_OFFICER_ADDRESS", "[Registered office address]"),
    "hours": env_str("GRIEVANCE_OFFICER_HOURS", "Monday to Friday, 10:00 to 18:00 IST"),
    "acknowledge_hours": env_int("GRIEVANCE_ACKNOWLEDGE_HOURS", 24),
    "resolve_days": env_int("GRIEVANCE_RESOLVE_DAYS", 15),
}
# Who hears about an account that turns out to belong to a minor.
TRUST_TEAM_EMAILS = env_list("TRUST_TEAM_EMAILS", "")
