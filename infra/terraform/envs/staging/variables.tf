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
