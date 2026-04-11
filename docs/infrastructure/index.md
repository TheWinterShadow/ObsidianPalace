---
title: Infrastructure
description: Terraform infrastructure for ObsidianPalace on GCP.
icon: material/server
---

# Infrastructure

All ObsidianPalace infrastructure is managed by Terraform, following the directories-over-workspaces pattern. State is stored in Terraform Cloud (org: `TheWinterShadow`, workspace: `obsidian-palace`).

## Directory Structure

```
terraform/
├── environments/
│   └── prod/
│       ├── versions.tf     # Terraform Cloud backend, provider versions
│       ├── provider.tf     # Google provider configuration
│       ├── variables.tf    # Root variables (pass-through to module)
│       ├── main.tf         # Module instantiation + health check
│       ├── outputs.tf      # Root outputs
│       └── backend.tf      # Commented-out GCS backend alternative
└── modules/
    └── obsidian_palace/
        ├── versions.tf     # Module provider requirements
        ├── variables.tf    # Module input variables
        ├── apis.tf         # GCP API enablement
        ├── secrets.tf      # Secret Manager resources + IAM
        ├── network.tf      # Static IP, firewall rules
        ├── compute.tf      # Service account, persistent disk, GCE instance
        ├── dns.tf          # Cloud DNS managed zone + A record
        ├── registry.tf     # Artifact Registry Docker repository
        └── outputs.tf      # Module outputs
```

## Resources Provisioned

### APIs Enabled

| API | Purpose |
|-----|---------|
| `compute.googleapis.com` | GCE instances, disks, firewall, static IPs |
| `secretmanager.googleapis.com` | Secret storage and retrieval |
| `dns.googleapis.com` | Cloud DNS managed zones |
| `artifactregistry.googleapis.com` | Docker image registry |

### Secret Manager

Five secrets are created, each with IAM bindings granting the GCE service account `roles/secretmanager.secretAccessor`:

| Secret | Content |
|--------|---------|
| `obsidian-palace-google-oauth-client-id` | Google OAuth client ID |
| `obsidian-palace-google-oauth-client-secret` | Google OAuth client secret |
| `obsidian-palace-allowed-email` | Authorized Google account email |
| `obsidian-palace-anthropic-api-key` | Anthropic API key for AI placement |
| `obsidian-palace-obsidian-sync-credentials` | Base64-encoded Obsidian Sync credential file |

### Networking

| Resource | Configuration |
|----------|---------------|
| **Static IP** | Regional external IP in `us-central1` |
| **Firewall: HTTPS** | Port 443 from all IPs (OAuth handles auth) |
| **Firewall: HTTP** | Port 80 from all IPs (Let's Encrypt ACME only) |
| **Firewall: SSH** | Port 22 from specified CIDRs only (optional) |

### Compute

| Resource | Configuration |
|----------|---------------|
| **Service Account** | `obsidian-palace@obsidianpalace.iam.gserviceaccount.com` |
| **IAM Roles** | Artifact Registry Reader, Log Writer, Metric Writer |
| **Boot Disk** | 10 GB pd-standard, Container-Optimized OS |
| **Data Disk** | 20 GB pd-standard, mounted at `/mnt/data` |
| **Machine Type** | e2-small (2 vCPU, 2 GB RAM) |

### DNS

| Resource | Configuration |
|----------|---------------|
| **Managed Zone** | `thewintershadow-com` for `thewintershadow.com.` |
| **A Record** | `lifeos.thewintershadow.com` pointing to static IP |

### Artifact Registry

| Resource | Configuration |
|----------|---------------|
| **Repository** | `obsidian-palace` (Docker format) in `us-central1` |
| **Cleanup** | Keeps the 5 most recent tagged images |

## Post-Deploy Health Check

The root module includes a `check {}` block that validates the service is reachable after deployment:

```hcl
check "health" {
  data "http" "health" {
    url = "https://lifeos.thewintershadow.com/health"
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
```

## Startup Sequence

The GCE instance runs a startup script (COS-compatible — no `apt-get`) that:

1. **Mounts the persistent disk** at `/mnt/data` (formats on first boot)
2. **Creates data directories** (`vault`, `chromadb`, `obsidian-config`, `letsencrypt`)
3. **Pulls secrets** from Secret Manager via `gcloud`
4. **Writes Obsidian Sync credentials** (base64-decoded) to disk
5. **Runs certbot in Docker** for Let's Encrypt SSL (first boot only)
6. **Symlinks certificates** to a stable path the container's nginx config expects
7. **Pulls and starts** the Docker container with all env vars and volume mounts
8. **Installs a cron job** for automatic certificate renewal (also runs certbot in Docker)
