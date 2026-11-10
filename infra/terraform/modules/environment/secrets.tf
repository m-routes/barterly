# Secret containers. The Django key is added out of band (infra/scripts/set-secrets.sh);
# DATABASE_URL is written by database.tf through a write-only argument. Neither value
# appears in Terraform state or in git.

locals {
  secrets = {
    django_secret_key = "django-secret-key-${local.env}"
    database_url      = "database-url-${local.env}" # Cloud SQL via the connector socket
  }

  secret_access = {
    api_secret_key       = { secret = "django_secret_key", member = google_service_account.api.member }
    api_database_url     = { secret = "database_url", member = google_service_account.api.member }
    migrate_secret_key   = { secret = "django_secret_key", member = google_service_account.migrate.member }
    migrate_database_url = { secret = "database_url", member = google_service_account.migrate.member }
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
