module "obsidian_palace" {
  source = "../../modules/obsidian_palace"

  project_id = var.project_id
  region     = var.region
  zone       = var.zone

  domain = var.domain

  container_image = var.container_image

  # Secrets — values from Terraform Cloud workspace variables.
  google_oauth_client_id     = var.google_oauth_client_id
  google_oauth_client_secret = var.google_oauth_client_secret
  allowed_email              = var.allowed_email
  anthropic_api_key          = var.anthropic_api_key

  # Network access.
  allowed_ssh_cidrs   = var.allowed_ssh_cidrs
  allowed_https_cidrs = var.allowed_https_cidrs
}

# --- Post-deploy health check ---

check "health" {
  data "http" "health" {
    url = "https://${var.domain}/health"

    retry {
      attempts     = 3
      min_delay_ms = 5000
    }
  }

  assert {
    condition     = data.http.health.status_code == 200
    error_message = "ObsidianPalace health endpoint did not return 200."
  }
}
