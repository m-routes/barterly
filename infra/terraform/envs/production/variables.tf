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

variable "firebase_web" {
  description = "Firebase web app config (public): Firebase console -> Project settings -> Your apps."
  type = object({
    api_key = string
    app_id  = string
  })
  default = { api_key = "", app_id = "" }
}
