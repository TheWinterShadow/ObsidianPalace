# Artifact Registry for ObsidianPalace Docker images.

resource "google_artifact_registry_repository" "obsidian_palace" {
  project       = var.project_id
  location      = var.region
  repository_id = "obsidian-palace"
  description   = "Docker images for ObsidianPalace MCP server."
  format        = "DOCKER"

  cleanup_policy_dry_run = false

  # Keep only the 5 most recent tagged images to save storage costs.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"

    most_recent_versions {
      keep_count = 5
    }
  }

  labels = {
    service = "obsidian-palace"
  }

  depends_on = [google_project_service.artifact_registry]
}
