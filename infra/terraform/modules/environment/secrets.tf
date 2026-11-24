# Secret containers. The Django key is added out of band (infra/scripts/set-secrets.sh);
# DATABASE_URL is written by database.tf through a write-only argument. Neither value
# appears in Terraform state or in git.

locals {
  secrets = {
    django_secret_key = "django-secret-key-${local.env}"
    database_url      = "database-url-${local.env}" # Cloud SQL via the connector socket
    # Razorpay (apps.billing); values added out of band like the Django key.
    razorpay_key_id         = "razorpay-key-id-${local.env}"
    razorpay_key_secret     = "razorpay-key-secret-${local.env}"
    razorpay_webhook_secret = "razorpay-webhook-secret-${local.env}"
    # The escrow webhook (apps.money) is a separate Razorpay webhook with its own secret.
    razorpay_escrow_webhook_secret = "razorpay-escrow-webhook-secret-${local.env}"
    # Payouts (RazorpayX): its own webhook secret, and the account payouts leave from.
    razorpayx_webhook_secret = "razorpayx-webhook-secret-${local.env}"
    razorpayx_account_number = "razorpayx-account-number-${local.env}"
    # Signs check-in passes (apps.attendance): 32 random bytes, base64.
    attendance_signing_key = "attendance-signing-key-${local.env}"
    # Field-level encryption keys (apps.common.encryption): "id:base64(32 bytes)", comma
    # separated, newest first. Rotation: infra/scripts/rotate-secrets.sh.
    field_encryption_keys = "field-encryption-keys-${local.env}"
    # Post stats (apps.deliverables): a YouTube Data API key; the Instagram Graph token
    # is added after Meta app review.
    youtube_api_key = "youtube-api-key-${local.env}"
    # Optional integrations, each wired only when its *_enabled variable is set.
    sentry_dsn            = "sentry-dsn-${local.env}"
    email_host_password   = "email-host-password-${local.env}"
    kyc_webhook_secret    = "kyc-webhook-secret-${local.env}"
    instagram_graph_token = "instagram-graph-token-${local.env}"
    # Cloud CDN signing key for media (edge.tf); written by infra/scripts/set-cdn-key.sh.
    media_cdn_key = "media-cdn-key-${local.env}"
  }

  secret_access = {
    api_secret_key       = { secret = "django_secret_key", member = google_service_account.api.member }
    api_database_url     = { secret = "database_url", member = google_service_account.api.member }
    migrate_secret_key   = { secret = "django_secret_key", member = google_service_account.migrate.member }
    migrate_database_url = { secret = "database_url", member = google_service_account.migrate.member }
    api_razorpay_key_id  = { secret = "razorpay_key_id", member = google_service_account.api.member }
    api_razorpay_secret  = { secret = "razorpay_key_secret", member = google_service_account.api.member }
    api_razorpay_webhook = { secret = "razorpay_webhook_secret", member = google_service_account.api.member }
    api_razorpay_escrow  = { secret = "razorpay_escrow_webhook_secret", member = google_service_account.api.member }
    api_razorpayx_hook   = { secret = "razorpayx_webhook_secret", member = google_service_account.api.member }
    api_razorpayx_acct   = { secret = "razorpayx_account_number", member = google_service_account.api.member }
    api_attendance_key   = { secret = "attendance_signing_key", member = google_service_account.api.member }
    migrate_attendance   = { secret = "attendance_signing_key", member = google_service_account.migrate.member }
    api_field_keys       = { secret = "field_encryption_keys", member = google_service_account.api.member }
    migrate_field_keys   = { secret = "field_encryption_keys", member = google_service_account.migrate.member }
    api_youtube_key      = { secret = "youtube_api_key", member = google_service_account.api.member }
    api_instagram_token  = { secret = "instagram_graph_token", member = google_service_account.api.member }
    api_sentry_dsn       = { secret = "sentry_dsn", member = google_service_account.api.member }
    web_sentry_dsn       = { secret = "sentry_dsn", member = google_service_account.web.member }
    api_email_password   = { secret = "email_host_password", member = google_service_account.api.member }
    api_kyc_webhook      = { secret = "kyc_webhook_secret", member = google_service_account.api.member }
    api_media_cdn_key    = { secret = "media_cdn_key", member = google_service_account.api.member }
  }
}

resource "google_secret_manager_secret" "this" {
  for_each = local.secrets

  secret_id = each.value
  labels = {
    app         = "barterly"
    environment = local.env
  }

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_iam_member" "access" {
  for_each = local.secret_access

  secret_id = google_secret_manager_secret.this[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}
