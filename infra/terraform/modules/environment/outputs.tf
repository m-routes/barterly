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

output "edge_ip" {
  description = "The load balancer's address: point every domain's A record here."
  value       = var.edge_enabled ? google_compute_global_address.edge[0].address : null
}

output "dns_records" {
  description = "DNS records to create at the registrar (docs/edge.md)."
  value = var.edge_enabled ? [
    for domain in distinct(concat(var.api_domains, var.web_domains, var.media_domain == "" ? [] : [var.media_domain])) :
    { name = domain, type = "A", value = google_compute_global_address.edge[0].address }
  ] : []
}

output "certificate_name" {
  description = "Check provisioning with: gcloud compute ssl-certificates describe <name> --global"
  value       = var.edge_enabled ? google_compute_managed_ssl_certificate.edge[0].name : null
}

output "media_backend_bucket" {
  description = "Backend bucket that holds the CDN signing key (set-cdn-key.sh)."
  value       = var.edge_enabled && var.media_domain != "" ? google_compute_backend_bucket.media[0].name : null
}
