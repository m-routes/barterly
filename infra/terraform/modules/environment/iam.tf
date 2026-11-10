# One runtime service account per workload, each with only what it uses.

resource "google_service_account" "api" {
  account_id   = "barterly-api-${local.env}"
  display_name = "Barterly API (${local.env})"
}

resource "google_service_account" "web" {
  account_id   = "barterly-web-${local.env}"
  display_name = "Barterly web (${local.env})"
}

resource "google_service_account" "migrate" {
  account_id   = "barterly-migrate-${local.env}"
  display_name = "Barterly migrate job (${local.env})"
}

resource "google_service_account" "deploy" {
  account_id   = "barterly-deploy-${local.env}"
  display_name = "Barterly GitHub deployer (${local.env})"
}

# The API signs media URLs through IAM signBlob as itself (no key file on Cloud Run).
resource "google_service_account_iam_member" "api_sign_blob" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = google_service_account.api.member
}

# --- Deployer: GitHub Actions jobs running in the matching GitHub environment ---

resource "google_service_account_iam_member" "deploy_wif" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${var.workload_identity_pool_name}/attribute.environment/${local.env}"
}

# Deploying a revision "as" a runtime service account requires actAs on it.
resource "google_service_account_iam_member" "deploy_act_as" {
  for_each = {
    api     = google_service_account.api.name
    web     = google_service_account.web.name
    migrate = google_service_account.migrate.name
  }

  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deploy.member
}

# Staging builds and pushes images; production only promotes images staging already ran.
resource "google_artifact_registry_repository_iam_member" "deploy" {
  location   = var.region
  repository = var.artifact_repository_id
  role       = local.env == "staging" ? "roles/artifactregistry.writer" : "roles/artifactregistry.reader"
  member     = google_service_account.deploy.member
}

resource "google_cloud_run_v2_service_iam_member" "deploy_api" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.developer"
  member   = google_service_account.deploy.member
}

resource "google_cloud_run_v2_service_iam_member" "deploy_web" {
  name     = google_cloud_run_v2_service.web.name
  location = var.region
  role     = "roles/run.developer"
  member   = google_service_account.deploy.member
}

resource "google_cloud_run_v2_job_iam_member" "deploy_migrate" {
  name     = google_cloud_run_v2_job.migrate.name
  location = var.region
  role     = "roles/run.developer"
  member   = google_service_account.deploy.member
}

# Read-only project access so gcloud can poll long-running operations and executions.
resource "google_project_iam_member" "deploy_run_viewer" {
  project = var.project_id
  role    = "roles/run.viewer"
  member  = google_service_account.deploy.member
}
