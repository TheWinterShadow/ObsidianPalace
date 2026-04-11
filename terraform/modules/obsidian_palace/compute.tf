# GCE instance, service account, persistent disk, and startup script.

# --- Service Account ---

resource "google_service_account" "obsidian_palace" {
  project      = var.project_id
  account_id   = "obsidian-palace"
  display_name = "ObsidianPalace MCP Server"

  depends_on = [google_project_service.compute]
}

# Allow the SA to pull from Artifact Registry.
resource "google_project_iam_member" "artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.obsidian_palace.email}"
}

# Allow the SA to write logs.
resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.obsidian_palace.email}"
}

# Allow the SA to export metrics.
resource "google_project_iam_member" "metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.obsidian_palace.email}"
}

# --- Persistent Disk ---

resource "google_compute_disk" "data" {
  project = var.project_id
  name    = "obsidian-palace-data"
  type    = "pd-standard"
  zone    = var.zone
  size    = var.disk_size_gb

  labels = {
    service = "obsidian-palace"
  }

  depends_on = [google_project_service.compute]
}

# --- Startup Script ---
# Mounts persistent disk, pulls secrets, runs the container.

locals {
  startup_script = <<-SCRIPT
    #!/bin/bash
    set -euo pipefail

    # --- Mount persistent disk ---
    DATA_DIR="/mnt/data"
    DEVICE="/dev/disk/by-id/google-obsidian-palace-data"

    mkdir -p "$DATA_DIR"

    # Format only if not already formatted.
    if ! blkid "$DEVICE" > /dev/null 2>&1; then
      mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0 "$DEVICE"
    fi

    mount -o discard,defaults "$DEVICE" "$DATA_DIR"
    mkdir -p "$DATA_DIR/vault" "$DATA_DIR/chromadb"

    # --- Pull secrets from Secret Manager ---
    fetch_secret() {
      gcloud secrets versions access latest --secret="$1" --project="${var.project_id}" 2>/dev/null
    }

    OAUTH_CLIENT_ID=$(fetch_secret "obsidian-palace-google-oauth-client-id")
    OAUTH_CLIENT_SECRET=$(fetch_secret "obsidian-palace-google-oauth-client-secret")
    ALLOWED_EMAIL=$(fetch_secret "obsidian-palace-allowed-email")
    ANTHROPIC_API_KEY=$(fetch_secret "obsidian-palace-anthropic-api-key")
    OBSIDIAN_SYNC_CREDS=$(fetch_secret "obsidian-palace-obsidian-sync-credentials")

    # --- Write Obsidian Sync credentials ---
    SYNC_CREDS_DIR="$DATA_DIR/obsidian-config"
    mkdir -p "$SYNC_CREDS_DIR"
    echo "$OBSIDIAN_SYNC_CREDS" | base64 -d > "$SYNC_CREDS_DIR/obsidian-creds.json"

    # --- Install and configure certbot for SSL ---
    if [ ! -f "/etc/letsencrypt/live/${var.domain}/fullchain.pem" ]; then
      apt-get update -qq && apt-get install -y -qq certbot
      certbot certonly --standalone --non-interactive --agree-tos \
        --email "$ALLOWED_EMAIL" \
        -d "${var.domain}"
    fi

    # --- Configure Docker auth for Artifact Registry ---
    gcloud auth configure-docker ${var.region}-docker.pkg.dev --quiet

    # --- Run the container ---
    docker pull ${var.container_image}

    docker run -d \
      --name obsidian-palace \
      --restart unless-stopped \
      -p 443:8080 \
      -p 80:8080 \
      -v "$DATA_DIR/vault:/data/vault" \
      -v "$DATA_DIR/chromadb:/data/chromadb" \
      -v "$SYNC_CREDS_DIR:/data/obsidian-config:ro" \
      -v "/etc/letsencrypt:/etc/letsencrypt:ro" \
      -e OBSIDIAN_PALACE_GOOGLE_CLIENT_ID="$OAUTH_CLIENT_ID" \
      -e OBSIDIAN_PALACE_GOOGLE_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
      -e OBSIDIAN_PALACE_ALLOWED_EMAIL="$ALLOWED_EMAIL" \
      -e OBSIDIAN_PALACE_ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
      -e OBSIDIAN_PALACE_VAULT_PATH="/data/vault" \
      -e OBSIDIAN_PALACE_CHROMADB_PATH="/data/chromadb" \
      -e OBSIDIAN_PALACE_HOST="0.0.0.0" \
      -e OBSIDIAN_PALACE_PORT="8080" \
      ${var.container_image}

    # --- Certbot auto-renewal cron ---
    echo "0 3 * * * certbot renew --quiet --deploy-hook 'docker restart obsidian-palace'" \
      | crontab -
  SCRIPT
}

# --- GCE Instance ---

resource "google_compute_instance" "obsidian_palace" {
  project      = var.project_id
  name         = "obsidian-palace"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["obsidian-palace"]

  boot_disk {
    initialize_params {
      image = "projects/cos-cloud/global/images/family/cos-stable"
      size  = 10
      type  = "pd-standard"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.self_link
    device_name = "obsidian-palace-data"
    mode        = "READ_WRITE"
  }

  network_interface {
    network = "default"

    access_config {
      nat_ip = google_compute_address.obsidian_palace.address
    }
  }

  metadata = {
    startup-script = local.startup_script
  }

  service_account {
    email  = google_service_account.obsidian_palace.email
    scopes = ["cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
  }

  labels = {
    service = "obsidian-palace"
  }

  allow_stopping_for_update = true

  depends_on = [
    google_project_service.compute,
    google_project_iam_member.artifact_reader,
    google_project_iam_member.log_writer,
  ]
}
