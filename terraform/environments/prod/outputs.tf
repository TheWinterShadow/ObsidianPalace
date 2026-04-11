output "instance_ip" {
  description = "Static external IP address of the ObsidianPalace GCE instance."
  value       = module.obsidian_palace.instance_ip
}

output "instance_name" {
  description = "Name of the GCE instance."
  value       = module.obsidian_palace.instance_name
}

output "service_url" {
  description = "HTTPS URL of the ObsidianPalace service."
  value       = module.obsidian_palace.service_url
}

output "dns_name_servers" {
  description = "Name servers for the DNS zone. Point your registrar NS records here."
  value       = module.obsidian_palace.dns_name_servers
}

output "service_account_email" {
  description = "Email of the ObsidianPalace service account."
  value       = module.obsidian_palace.service_account_email
}

output "artifact_registry_url" {
  description = "Base URL for pushing Docker images to Artifact Registry."
  value       = module.obsidian_palace.artifact_registry_url
}
