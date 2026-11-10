# One Barterly environment (staging or production): service accounts, secrets,
# buckets, Cloud SQL, Cloud Run services (api, web) and the migrate job.

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  env            = var.environment
  project_number = data.google_project.this.number
  registry       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repository_id}"

  api_name     = "barterly-api-${local.env}"
  web_name     = "barterly-web-${local.env}"
  migrate_name = "barterly-migrate-${local.env}"

  # Deterministic Cloud Run URLs: https://SERVICE-PROJECT_NUMBER.REGION.run.app
  api_run_host       = "${local.api_name}-${local.project_number}.${var.region}.run.app"
  api_candidate_host = "candidate---${local.api_run_host}"
  web_run_host       = "${local.web_name}-${local.project_number}.${var.region}.run.app"

  api_hosts = concat([local.api_run_host, local.api_candidate_host], var.api_domains)
  api_url   = length(var.api_domains) > 0 ? "https://${var.api_domains[0]}" : "https://${local.api_run_host}"
  web_origins = concat(
    ["https://${local.web_run_host}"],
    [for d in var.web_domains : "https://${d}"],
  )

  settings_module = "config.settings.${local.env}"
}
