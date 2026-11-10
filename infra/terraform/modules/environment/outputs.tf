output "api_url" {
  value = local.api_url
}

output "api_run_url" {
  value = "https://${local.api_run_host}"
}

output "web_run_url" {
  value = "https://${local.web_run_host}"
}

output "deploy_service_account" {
  description = "Value for the GCP_DEPLOY_SA variable of the matching GitHub environment."
  value       = google_service_account.deploy.email
}

output "project_number" {
  description = "Value for the GCP_PROJECT_NUMBER GitHub variable."
  value       = local.project_number
}

output "media_bucket" {
  value = google_storage_bucket.media.name
}

output "static_bucket" {
  value = google_storage_bucket.static.name
}

output "secret_ids" {
  value = { for k, s in google_secret_manager_secret.this : k => s.secret_id }
}

output "database_instance" {
  description = "Cloud SQL connection name (PROJECT:REGION:INSTANCE)."
  value       = google_sql_database_instance.main.connection_name
}
