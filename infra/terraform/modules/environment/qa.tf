# Acceptance testing on staging (docs/qa/README.md). Off unless var.qa_enabled.
#
# - barterly-qa-<env>: a Cloud Run job that runs the seed commands
#   (`seed_staging`, `prepare_journey`) with the API's image and identity; the nightly
#   workflow executes it before each acceptance run. Production settings refuse to
#   seed whatever runs them (ALLOW_SEED is forced off).
# - qa-admin-password-<env>: the admin persona's back-office password, shared with
#   the workflow as the E2E_ADMIN_PASSWORD secret. Add a value out of band.
# - FIREBASE_TEST_NUMBERS_ALLOWED on the web: sign-in may use Firebase test numbers
#   when a page asks for it (web/src/lib/server/env.ts).

resource "google_secret_manager_secret" "qa_admin_password" {
  count     = var.qa_enabled ? 1 : 0
  secret_id = "qa-admin-password-${local.env}"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "qa_admin_password" {
  count     = var.qa_enabled ? 1 : 0
  secret_id = google_secret_manager_secret.qa_admin_password[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.api.member
}

resource "google_cloud_run_v2_job" "qa" {
  count               = var.qa_enabled ? 1 : 0
  name                = "barterly-qa-${local.env}"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1

    template {
      service_account = google_service_account.api.email
      timeout         = "600s"
      max_retries     = 0

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }

      containers {
        image   = var.bootstrap_image
        command = ["python", "manage.py"]
        args    = ["seed_staging"]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi" # agreement PDFs render here
          }
        }

        dynamic "env" {
          for_each = merge(local.deployed_env, {
            GS_SA_EMAIL      = google_service_account.api.email
            DB_POOL_MAX_SIZE = "2"
          })
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = {
            DJANGO_SECRET_KEY      = google_secret_manager_secret.this["django_secret_key"].secret_id
            DATABASE_URL           = google_secret_manager_secret.this["database_url"].secret_id
            ATTENDANCE_SIGNING_KEY = google_secret_manager_secret.this["attendance_signing_key"].secret_id
            FIELD_ENCRYPTION_KEYS  = google_secret_manager_secret.this["field_encryption_keys"].secret_id
            SEED_ADMIN_PASSWORD    = google_secret_manager_secret.qa_admin_password[0].secret_id
          }
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }

  lifecycle {
    # deploy.sh moves it to each release's image, like the migrate job.
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.access,
    google_secret_manager_secret_iam_member.qa_admin_password,
    google_project_iam_member.cloudsql_client,
  ]
}
