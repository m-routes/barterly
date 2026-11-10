output "artifact_repository_id" {
  value = google_artifact_registry_repository.docker.repository_id
}

output "registry_url" {
  description = "Docker registry prefix for images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

output "workload_identity_pool_name" {
  value = google_iam_workload_identity_pool.github.name
}

output "workload_identity_provider_name" {
  description = "Value for the GCP_WIF_PROVIDER GitHub variable."
  value       = google_iam_workload_identity_pool_provider.github.name
}
