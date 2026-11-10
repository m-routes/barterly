terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.10, < 8.0"
    }
  }

  # Configured at init time: terraform init -backend-config="bucket=<state bucket>"
  backend "gcs" {
    prefix = "shared"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
