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

variable "qa_enabled" {
  description = "Acceptance testing: the QA job, its admin password secret and test-number sign-in (staging only)."
  type        = bool
  default     = false
}
