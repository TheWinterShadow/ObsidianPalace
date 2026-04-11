# GCE instance, service account, persistent disk, and startup script.

# --- Service Account ---

resource "google_service_account" "obsidian_palace" {
  project      = var.project_id
  account_id   = "obsidian-palace"
  display_name = "ObsidianPalace MCP Server"

  depends_on = [
    google_project_service.compute,
    google_project_service.iam,
  ]
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

    log() { echo "[startup] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

    # --- Mount persistent disk ---
    DATA_DIR="/mnt/disks/data"
    DEVICE="/dev/disk/by-id/google-obsidian-palace-data"

    mkdir -p "$DATA_DIR"

    # Format only if not already formatted.
    if ! blkid "$DEVICE" > /dev/null 2>&1; then
      log "Formatting persistent disk"
      mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0 "$DEVICE"
    fi

    mount -o discard,defaults "$DEVICE" "$DATA_DIR"
    mkdir -p "$DATA_DIR/vault" "$DATA_DIR/chromadb" "$DATA_DIR/obsidian-config"
    mkdir -p "$DATA_DIR/letsencrypt" "$DATA_DIR/certbot-webroot"

    # --- Pull secrets from Secret Manager ---
    # COS has no gcloud on the host; use the cloud-sdk Docker image.
    GCLOUD_IMAGE="gcr.io/google.com/cloudsdktool/google-cloud-cli:slim"
    fetch_secret() {
      docker run --rm "$GCLOUD_IMAGE" \
        gcloud secrets versions access latest \
          --secret="$1" --project="${var.project_id}"
    }

    log "Fetching secrets from Secret Manager"
    OAUTH_CLIENT_ID=$(fetch_secret "obsidian-palace-google-oauth-client-id")
    OAUTH_CLIENT_SECRET=$(fetch_secret "obsidian-palace-google-oauth-client-secret")
    ALLOWED_EMAIL=$(fetch_secret "obsidian-palace-allowed-email")
    ANTHROPIC_API_KEY=$(fetch_secret "obsidian-palace-anthropic-api-key")
    OBSIDIAN_SYNC_CREDS=$(fetch_secret "obsidian-palace-obsidian-sync-credentials")

    # --- Write Obsidian Sync credentials ---
    # obsidian-headless reads ~/.obsidian-headless/auth_token (plain text).
    echo "$OBSIDIAN_SYNC_CREDS" | base64 -d > "$DATA_DIR/obsidian-config/auth_token"
    chmod 600 "$DATA_DIR/obsidian-config/auth_token"
    log "Obsidian Sync credentials written"

    # --- SSL certificate via certbot (runs in Docker on COS) ---
    CERT_DIR="$DATA_DIR/letsencrypt"

    if [ ! -f "$CERT_DIR/live/${var.domain}/fullchain.pem" ]; then
      log "Obtaining SSL certificate for ${var.domain} via certbot"
      docker run --rm \
        -v "$CERT_DIR:/etc/letsencrypt" \
        -v "$DATA_DIR/certbot-webroot:/var/www/certbot" \
        -p 80:80 \
        certbot/certbot certonly \
          --standalone \
          --non-interactive \
          --agree-tos \
          --email "$ALLOWED_EMAIL" \
          -d "${var.domain}"
      log "SSL certificate obtained"
    else
      log "SSL certificate already exists — skipping certbot"
    fi

    # Symlink certs to a stable path the container expects.
    # The nginx.conf references /etc/letsencrypt/live/certs/*.pem
    # Use relative symlinks so they resolve inside the container too.
    mkdir -p "$CERT_DIR/live/certs"
    if [ -d "$CERT_DIR/live/${var.domain}" ]; then
      cd "$CERT_DIR/live/certs"
      ln -sf "../${var.domain}/fullchain.pem" fullchain.pem
      ln -sf "../${var.domain}/privkey.pem" privkey.pem
      cd /
    fi

    # --- Configure Docker auth for Artifact Registry ---
    # COS root filesystem is read-only; write Docker config to the data disk.
    DOCKER_CONFIG="$DATA_DIR/docker-config"
    mkdir -p "$DOCKER_CONFIG"
    cat > "$DOCKER_CONFIG/config.json" <<DOCKERCFG
    {
      "credHelpers": {
        "${var.region}-docker.pkg.dev": "gcr"
      }
    }
    DOCKERCFG

    # --- Stop and remove any existing container ---
    docker rm -f obsidian-palace 2>/dev/null || true

    # --- Pull and run the container ---
    log "Pulling container image: ${var.container_image}"
    docker --config "$DOCKER_CONFIG" pull ${var.container_image}

    log "Starting ObsidianPalace container"
    docker run -d \
      --name obsidian-palace \
      --restart unless-stopped \
      -p 443:443 \
      -p 80:80 \
      -v "$DATA_DIR/vault:/data/vault" \
      -v "$DATA_DIR/chromadb:/data/chromadb" \
      -v "$DATA_DIR/obsidian-config:/data/obsidian-config:ro" \
      -v "$CERT_DIR:/etc/letsencrypt:ro" \
      -v "$DATA_DIR/certbot-webroot:/var/www/certbot" \
      -e OBSIDIAN_PALACE_GOOGLE_CLIENT_ID="$OAUTH_CLIENT_ID" \
      -e OBSIDIAN_PALACE_GOOGLE_CLIENT_SECRET="$OAUTH_CLIENT_SECRET" \
      -e OBSIDIAN_PALACE_ALLOWED_EMAIL="$ALLOWED_EMAIL" \
      -e OBSIDIAN_PALACE_ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
      -e OBSIDIAN_PALACE_VAULT_PATH="/data/vault" \
      -e OBSIDIAN_PALACE_CHROMADB_PATH="/data/chromadb" \
      -e OBSIDIAN_PALACE_HOST="0.0.0.0" \
      -e OBSIDIAN_PALACE_PORT="8080" \
      ${var.container_image}

    log "Container started"

    # --- Certbot auto-renewal ---
    # COS root filesystem is read-only, so /etc/cron.daily is not writable.
    # Write a renewal script to the data disk and schedule via systemd timer.
    cat > "$DATA_DIR/certbot-renew.sh" <<'CRON'
    #!/bin/bash
    # Stop nginx in the container to free port 80 for certbot standalone.
    docker exec obsidian-palace supervisorctl stop nginx 2>/dev/null || true
    docker run --rm \
      -v /mnt/disks/data/letsencrypt:/etc/letsencrypt \
      -p 80:80 \
      certbot/certbot renew --quiet
    docker exec obsidian-palace supervisorctl start nginx 2>/dev/null || true
    CRON
    chmod +x "$DATA_DIR/certbot-renew.sh"

    log "Startup complete"
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
