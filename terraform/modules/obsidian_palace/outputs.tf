output "instance_ip" {
  description = "Static external IP address of the ObsidianPalace GCE instance."
  value       = google_compute_address.obsidian_palace.address
}

output "instance_name" {
  description = "Name of the GCE instance."
  value       = google_compute_instance.obsidian_palace.name
}

output "service_account_email" {
  description = "Email of the ObsidianPalace service account."
  value       = google_service_account.obsidian_palace.email
}

output "service_url" {
  description = "HTTPS URL of the ObsidianPalace service."
  value       = "https://${var.domain}"
}

output "data_disk_name" {
  description = "Name of the persistent data disk."
  value       = google_compute_disk.data.name
}

output "artifact_registry_url" {
  description = "Base URL for the Artifact Registry Docker repository."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.obsidian_palace.repository_id}"
}
