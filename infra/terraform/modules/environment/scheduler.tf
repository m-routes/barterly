# Cloud Scheduler runs the API's jobs by calling POST /api/v1/jobs/<name>/ with a
# Google-signed OIDC token for this service account. The API checks the token's
# signature, its audience (the API's URL) and that it was issued to this account
# (apps/bookings/scheduler.py); the jobs themselves are idempotent.

resource "google_service_account" "scheduler" {
  account_id   = "barterly-scheduler-${local.env}"
  display_name = "Barterly scheduled jobs (${local.env})"
}

locals {
  # Schedules are in India time.
  scheduled_jobs = {
    expire_offers            = { schedule = "*/15 * * * *", description = "Offers expire 48 hours after the last offer or counter." }
    flag_stale_interviews    = { schedule = "0 9 * * *", description = "Flag interviews with no movement for a week." }
    close_expired_gigs       = { schedule = "15 0 * * *", description = "Close gigs whose apply-by date has passed." }
    expire_verifications     = { schedule = "30 0 * * *", description = "Expire verifications past their validity." }
    sync_kyc_results         = { schedule = "*/30 * * * *", description = "Poll the KYC provider for missing results." }
    run_search_alerts        = { schedule = "0 */6 * * *", description = "Send saved-search alerts for new gigs." }
    send_interview_reminders = { schedule = "*/5 * * * *", description = "Interview reminders a day and an hour before." }
    render_agreements        = { schedule = "*/10 * * * *", description = "Draw up agreement PDFs a failed render left behind." }
    send_reminders           = { schedule = "5 * * * *", description = "Offers about to expire, agreements to sign, stays starting tomorrow." }
    dispatch_notifications   = { schedule = "*/5 * * * *", description = "Queue notifications held for quiet hours, or whose task went missing." }
  }
}

resource "google_cloud_scheduler_job" "jobs" {
  for_each = local.scheduled_jobs

  name             = "barterly-${local.env}-${replace(each.key, "_", "-")}"
  description      = each.value.description
  region           = var.region
  schedule         = each.value.schedule
  time_zone        = "Asia/Kolkata"
  attempt_deadline = "300s"

  retry_config {
    retry_count          = 3
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
  }

  http_target {
    http_method = "POST"
    uri         = "${local.api_url}/api/v1/jobs/${each.key}/"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = local.api_url
    }
  }
}
