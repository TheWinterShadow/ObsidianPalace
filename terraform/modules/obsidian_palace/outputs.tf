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

output "dns_name_servers" {
  description = "Name servers for the managed DNS zone. Point your registrar here."
  value       = google_dns_managed_zone.obsidian_palace.name_servers
}

output "service_url" {
  description = "HTTPS URL of the ObsidianPalace service."
  value       = "https://${var.domain}"
}

output "data_disk_name" {
  description = "Name of the persistent data disk."
  value       = google_compute_disk.data.name
}
