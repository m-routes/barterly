# Cloud Run services and the migrate job. Terraform owns configuration; CI owns the
# image and traffic split (infra/scripts/deploy.sh), so those are ignored here.

locals {

  deployed_env = {
    DJANGO_SETTINGS_MODULE      = local.settings_module
    DJANGO_ALLOWED_HOSTS        = join(",", local.api_hosts)
    DJANGO_CSRF_TRUSTED_ORIGINS = join(",", concat([for h in local.api_hosts : "https://${h}"], local.web_origins))
    GS_MEDIA_BUCKET             = google_storage_bucket.media.name
    GS_STATIC_BUCKET            = google_storage_bucket.static.name
    # Firebase Auth lives in the same Google Cloud project; ID tokens are checked
    # against it (public certificates only, no key).
    FIREBASE_PROJECT_ID = var.project_id
  }
}

resource "google_cloud_run_v2_service" "api" {
  name                = local.api_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  template {
    service_account                  = google_service_account.api.email
    timeout                          = "60s"
    max_instance_request_concurrency = 40

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = var.api_max_instances
    }

    containers {
      image = var.bootstrap_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = merge(local.deployed_env, {
          GS_SA_EMAIL      = google_service_account.api.email
          WEB_CONCURRENCY  = tostring(var.api_workers)
          DB_POOL_MAX_SIZE = tostring(var.db_pool_max_size)
        })
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name = "DJANGO_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["django_secret_key"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["database_url"].secret_id
            version = "latest"
          }
        }
      }

      # TCP only: an HTTP probe would hit the database and fail during a Cloud SQL restart.
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      startup_probe {
        tcp_socket {
          port = 8080
        }
        period_seconds    = 2
        failure_threshold = 30
        timeout_seconds   = 1
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      traffic,
    ]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.access,
    google_secret_manager_secret_version.database_url,
    google_project_iam_member.cloudsql_client,
  ]
}

resource "google_cloud_run_v2_service" "web" {
  name                = local.web_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  template {
    service_account                  = google_service_account.web.email
    timeout                          = "60s"
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = var.web_min_instances
      max_instance_count = var.web_max_instances
    }

    containers {
      image = var.bootstrap_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "API_URL"
        value = local.api_url
      }

      env {
        name  = "BARTERLY_ENV"
        value = local.env
      }

      # Phone sign-in (Firebase web SDK). Read at request time by the login page.
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "FIREBASE_WEB_API_KEY"
        value = var.firebase_web.api_key
      }

      env {
        name  = "FIREBASE_WEB_APP_ID"
        value = var.firebase_web.app_id
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      traffic,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "web_public" {
  name     = google_cloud_run_v2_service.web.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Runs `python manage.py release` (migrate + collectstatic) before each API revision
# gets traffic, through the same connector socket as the API.
resource "google_cloud_run_v2_job" "migrate" {
  name                = local.migrate_name
  location            = var.region
  deletion_protection = var.deletion_protection

  template {
    task_count = 1

    template {
      service_account = google_service_account.migrate.email
      timeout         = "900s"
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
        args    = ["release"]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        dynamic "env" {
          for_each = merge(local.deployed_env, { DB_POOL_MAX_SIZE = "2" })
          content {
            name  = env.key
            value = env.value
          }
        }

        env {
          name = "DJANGO_SECRET_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this["django_secret_key"].secret_id
              version = "latest"
            }
          }
        }

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this["database_url"].secret_id
              version = "latest"
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
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.access,
    google_secret_manager_secret_version.database_url,
    google_project_iam_member.cloudsql_client,
  ]
}
