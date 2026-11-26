variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "asia-south1"
}

variable "state_bucket" {
  description = "GCS bucket holding Terraform state (created by infra/scripts/bootstrap.sh)."
  type        = string
}

variable "api_domains" {
  type    = list(string)
  default = []
}

variable "web_domains" {
  type    = list(string)
  default = []
}

variable "firebase_project_id" {
  description = "The Firebase project id (Firebase console -> Project settings). Empty = project_id."
  type        = string
  default     = ""
}

variable "razorpay_enabled" {
  description = "Wire the Razorpay and RazorpayX secrets into the API. The live keys must have values before an apply (set-razorpay-secrets.sh)."
  type        = bool
  default     = true
}

variable "firebase_web" {
  description = "Firebase web app config (public): Firebase console -> Project settings -> Your apps."
  type = object({
    api_key = string
    app_id  = string
  })
  default = { api_key = "", app_id = "" }
}

variable "alert_emails" {
  description = "Who gets monitoring alerts (modules/environment/monitoring.tf)."
  type        = list(string)
  default     = []
}

variable "edge_enabled" {
  description = "Global HTTPS load balancer + Cloud Armor + Cloud CDN for the domains (docs/edge.md)."
  type        = bool
  default     = true
}

variable "media_domain" {
  description = "Media through Cloud CDN, e.g. media.barterly.in (empty: Cloud Storage signed URLs)."
  type        = string
  default     = ""
}

variable "media_cdn_signing_enabled" {
  description = "Set after infra/scripts/set-cdn-key.sh production has added the CDN signing key."
  type        = bool
  default     = false
}

variable "armor_preview" {
  description = "Cloud Armor rules log instead of block (use for the first days after enabling)."
  type        = bool
  default     = false
}
