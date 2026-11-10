variable "project_id" {
  description = "GCP project that hosts Barterly."
  type        = string
}

variable "region" {
  description = "GCP region for all regional resources."
  type        = string
  default     = "asia-south1"
}

variable "github_repository" {
  description = "GitHub repository allowed to deploy, as owner/name."
  type        = string
}

variable "artifact_repository_id" {
  description = "Artifact Registry Docker repository name."
  type        = string
  default     = "barterly"
}
