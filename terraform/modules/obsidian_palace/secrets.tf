# Secret Manager — all sensitive values injected into the container at startup.

locals {
  secrets = {
    google-oauth-client-id     = var.google_oauth_client_id
    google-oauth-client-secret = var.google_oauth_client_secret
    allowed-email              = var.allowed_email
    anthropic-api-key          = var.anthropic_api_key
  }
}

resource "google_secret_manager_secret" "secrets" {
  for_each = local.secrets

  project   = var.project_id
  secret_id = "obsidian-palace-${each.key}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "secrets" {
  for_each = local.secrets

  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = each.value
}

# Grant the GCE service account access to read secrets.
resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = local.secrets

  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.obsidian_palace.email}"
}
