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
