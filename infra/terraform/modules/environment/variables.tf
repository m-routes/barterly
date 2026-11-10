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
