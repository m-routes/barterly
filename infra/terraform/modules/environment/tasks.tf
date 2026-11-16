# Cloud Tasks: background work the API queues for itself, notification delivery above
# all. Each task is an HTTP POST to /api/v1/tasks/<name>/ with a Google-signed OIDC token
# for the tasks service account; the API checks it (apps/bookings/scheduler.py) and runs
# the task. A task that fails gets a 503 and is retried here with exponential backoff.
# Keep max_attempts at or above NOTIFICATION_MAX_ATTEMPTS: the API marks a delivery a
# dead letter itself after that many tries (the admin's dead-letter view).

resource "google_service_account" "tasks" {
  account_id   = "barterly-tasks-${local.env}"
  display_name = "Barterly background tasks (${local.env})"
}

resource "google_cloud_tasks_queue" "tasks" {
  name     = "barterly-${local.env}"
  location = var.region

  rate_limits {
    max_dispatches_per_second = 50
    max_concurrent_dispatches = 20
  }

  retry_config {
    max_attempts       = 8
    min_backoff        = "10s"
    max_backoff        = "600s"
    max_doublings      = 5
    max_retry_duration = "7200s"
  }

  stackdriver_logging_config {
    sampling_ratio = 1.0
  }
}

# The API creates tasks on its queue...
resource "google_cloud_tasks_queue_iam_member" "api_enqueue" {
  name     = google_cloud_tasks_queue.tasks.name
  location = var.region
  role     = "roles/cloudtasks.enqueuer"
  member   = google_service_account.api.member
}

# ...that carry an OIDC token for the tasks account, which needs actAs on it.
resource "google_service_account_iam_member" "api_act_as_tasks" {
  service_account_id = google_service_account.tasks.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.api.member
}

# Push notifications: the API sends through FCM as itself.
resource "google_project_iam_member" "api_fcm" {
  project = var.project_id
  role    = "roles/firebasecloudmessaging.admin"
  member  = google_service_account.api.member
}
