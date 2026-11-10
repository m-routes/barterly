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
    prefix = "staging"
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
  environment                 = "staging"
  artifact_repository_id      = data.terraform_remote_state.shared.outputs.artifact_repository_id
  workload_identity_pool_name = data.terraform_remote_state.shared.outputs.workload_identity_pool_name

  api_domains = var.api_domains
  web_domains = var.web_domains

  api_min_instances   = 0
  web_min_instances   = 0
  deletion_protection = false
  media_versioning    = false

  # Smallest shared-core tier (~25 connections): 2 instances x 2 workers x 4 = 16.
  api_max_instances    = 2
  db_tier              = "db-f1-micro"
  db_high_availability = false
  db_backup_retention  = 7
}

output "environment" {
  value = module.environment
}
