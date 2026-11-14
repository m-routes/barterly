terraform {
  required_version = ">= 1.11" # ephemeral resources and write-only arguments

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.0, < 8.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.7, < 4.0"
    }
  }

  # terraform init -backend-config="bucket=<state bucket>"
  backend "gcs" {
    prefix = "production"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "terraform_remote_state" "shared" {
  backend = "gcs"
  config = {
    bucket = var.state_bucket
    prefix = "shared"
  }
}

module "environment" {
  source = "../../modules/environment"

  project_id                  = var.project_id
  region                      = var.region
  environment                 = "production"
  artifact_repository_id      = data.terraform_remote_state.shared.outputs.artifact_repository_id
  workload_identity_pool_name = data.terraform_remote_state.shared.outputs.workload_identity_pool_name

  api_domains = var.api_domains
  web_domains = var.web_domains

  firebase_web = var.firebase_web

  api_min_instances   = 1
  web_min_instances   = 1
  deletion_protection = true
  media_versioning    = true

  # db-custom-1-3840 (~100 connections): 10 instances x 2 workers x 4 = 80.
  api_max_instances    = 10
  db_tier              = "db-custom-1-3840"
  db_high_availability = true
  db_backup_retention  = 30
}

output "environment" {
  value = module.environment
}
