variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "asia-south1"
}

variable "environment" {
  description = "staging or production."
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "artifact_repository_id" {
  description = "Artifact Registry repository (from the shared root)."
  type        = string
}

variable "workload_identity_pool_name" {
  description = "Full resource name of the GitHub workload identity pool (from the shared root)."
  type        = string
}

variable "bootstrap_image" {
  description = "Placeholder image for the first apply. CI deploys real images afterwards; Terraform ignores image changes."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "api_domains" {
  description = "Custom domains for the API (added to ALLOWED_HOSTS and CSRF origins)."
  type        = list(string)
  default     = []
}

variable "web_domains" {
  description = "Custom domains for the web console (CORS on the static bucket)."
  type        = list(string)
  default     = []
}

variable "api_min_instances" {
  type    = number
  default = 0
}

variable "api_max_instances" {
  type    = number
  default = 10
}

variable "web_min_instances" {
  type    = number
  default = 0
}

variable "web_max_instances" {
  type    = number
  default = 10
}

variable "deletion_protection" {
  description = "Protect Cloud Run services and buckets from terraform destroy."
  type        = bool
  default     = true
}

variable "media_versioning" {
  description = "Keep noncurrent versions of media objects."
  type        = bool
  default     = true
}

variable "api_workers" {
  description = "Gunicorn workers per API instance (WEB_CONCURRENCY)."
  type        = number
  default     = 2
}

variable "db_tier" {
  description = "Cloud SQL machine tier. db-f1-micro allows about 25 connections; db-custom-1-3840 about 100."
  type        = string
  default     = "db-custom-1-3840"
}

variable "db_high_availability" {
  description = "Regional (standby in a second zone) instead of zonal."
  type        = bool
  default     = true
}

variable "db_disk_size_gb" {
  type    = number
  default = 10
}

variable "db_backup_retention" {
  description = "Number of daily automated backups to keep."
  type        = number
  default     = 14
}

variable "db_password_version" {
  description = "Bump to generate a new database password and DATABASE_URL secret version."
  type        = number
  default     = 1
}

variable "db_pool_max_size" {
  description = "Connections per API worker. Keep api_max_instances x api_workers x this (+2 for the migrate job) under the tier's max_connections."
  type        = number
  default     = 4
}

variable "firebase_web" {
  description = <<-EOT
    Firebase web app config for phone sign-in on the web console (Firebase console ->
    Project settings -> Your apps). Public values, not secrets. Empty = sign-in shows
    "not available".
  EOT
  type = object({
    api_key = string
    app_id  = string
  })
  default = { api_key = "", app_id = "" }
}

variable "youtube_stats_enabled" {
  description = "Wire YOUTUBE_API_KEY into the API (add the secret's value first)."
  type        = bool
  default     = false
}

variable "instagram_stats_enabled" {
  description = "Fetch Instagram post stats. Needs Meta app review, the Graph token secret and the business account id."
  type        = bool
  default     = false
}

variable "instagram_business_account_id" {
  description = "Barterly's Instagram business account id (for business discovery)."
  type        = string
  default     = ""
}

variable "sentry_enabled" {
  description = "Send errors to Sentry (add the sentry-dsn secret's value first)."
  type        = bool
  default     = false
}

variable "email_enabled" {
  description = "Wire EMAIL_HOST_PASSWORD (add the email-host-password secret's value first)."
  type        = bool
  default     = false
}

variable "kyc_webhook_enabled" {
  description = "Wire KYC_WEBHOOK_SECRET (add the kyc-webhook-secret value first)."
  type        = bool
  default     = false
}

variable "clamav_enabled" {
  description = "Run clamd beside the API and scan every upload before it's served."
  type        = bool
  default     = false
}

variable "clamav_image" {
  description = "The clamd image (official ClamAV, pinned)."
  type        = string
  default     = "clamav/clamav:1.4.3"
}

# ---------- Monitoring (monitoring.tf) ----------

variable "alert_emails" {
  description = "Who gets alerts. Empty: metrics, uptime checks and the SLO exist, no alerts."
  type        = list(string)
  default     = []
}

variable "availability_slo" {
  description = "Share of API requests that must succeed over 28 days (docs/slo.md)."
  type        = number
  default     = 0.995
}

variable "error_rate_alert" {
  description = "5xx share of requests over 10 minutes that alerts."
  type        = number
  default     = 0.02
}

variable "latency_p95_alert_ms" {
  description = "p95 request latency (ms) over 10 minutes that alerts."
  type        = number
  default     = 1500
}

variable "queue_depth_alert" {
  description = "Cloud Tasks waiting for 15 minutes that alerts."
  type        = number
  default     = 200
}

variable "db_connection_alert" {
  description = "Open database connections that alert (set near the tier's limit)."
  type        = number
  default     = 80
}
