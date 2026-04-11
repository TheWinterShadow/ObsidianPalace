# Static IP and firewall rules.

resource "google_compute_address" "obsidian_palace" {
  project = var.project_id
  name    = "obsidian-palace-ip"
  region  = var.region

  depends_on = [google_project_service.compute]
}

# Allow HTTPS (443) from specified CIDRs.
# Anthropic's Claude clients and personal access.
resource "google_compute_firewall" "allow_https" {
  project = var.project_id
  name    = "obsidian-palace-allow-https"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  # Allow from anywhere — OAuth handles authentication.
  # MCP clients (Claude Desktop, iOS, claude.ai) connect from varied IPs.
  source_ranges = length(var.allowed_https_cidrs) > 0 ? var.allowed_https_cidrs : ["0.0.0.0/0"]

  target_tags = ["obsidian-palace"]

  depends_on = [google_project_service.compute]
}

# Allow HTTP (80) for Let's Encrypt ACME challenge only.
resource "google_compute_firewall" "allow_http" {
  project = var.project_id
  name    = "obsidian-palace-allow-http"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["obsidian-palace"]

  depends_on = [google_project_service.compute]
}

# SSH access — locked to specific CIDRs if provided.
resource "google_compute_firewall" "allow_ssh" {
  count = length(var.allowed_ssh_cidrs) > 0 ? 1 : 0

  project = var.project_id
  name    = "obsidian-palace-allow-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.allowed_ssh_cidrs
  target_tags   = ["obsidian-palace"]

  depends_on = [google_project_service.compute]
}
