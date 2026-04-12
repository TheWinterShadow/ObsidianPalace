---
title: Infrastructure
description: Terraform infrastructure for ObsidianPalace on GCP.
icon: material/server
---

# Infrastructure

All ObsidianPalace infrastructure is managed by Terraform, following the directories-over-workspaces pattern. State is stored in Terraform Cloud.

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
        ├── registry.tf     # Artifact Registry Docker repository
        └── outputs.tf      # Module outputs
```

## Resources Provisioned

### APIs Enabled

| API | Purpose |
|-----|---------|
| `compute.googleapis.com` | GCE instances, disks, firewall, static IPs |
| `secretmanager.googleapis.com` | Secret storage and retrieval |
| `artifactregistry.googleapis.com` | Docker image registry |
| `iam.googleapis.com` | Service account and IAM management |

### Secret Manager

Four secrets are created, each with IAM bindings granting the GCE service account `roles/secretmanager.secretAccessor`:

| Secret | Content |
|--------|---------|
| `obsidian-palace-google-oauth-client-id` | Google OAuth client ID |
| `obsidian-palace-google-oauth-client-secret` | Google OAuth client secret |
| `obsidian-palace-allowed-email` | Authorized Google account email |
| `obsidian-palace-anthropic-api-key` | Anthropic API key for AI placement |

### Networking

| Resource | Configuration |
|----------|---------------|
| **Static IP** | Regional external IP |
| **Firewall: HTTPS** | Port 443 from all IPs (OAuth handles auth) |
| **Firewall: HTTP** | Port 80 from all IPs (Let's Encrypt ACME only) |
| **Firewall: SSH** | Port 22 from specified CIDRs only (optional) |

### Compute

| Resource | Configuration |
|----------|---------------|
| **Service Account** | `obsidian-palace@YOUR_PROJECT_ID.iam.gserviceaccount.com` |
| **IAM Roles** | Artifact Registry Reader, Log Writer, Metric Writer |
| **Boot Disk** | 10 GB pd-standard, Container-Optimized OS |
| **Data Disk** | 20 GB pd-standard, mounted at `/mnt/disks/data` |
| **Machine Type** | e2-small (2 vCPU, 2 GB RAM) |

### DNS

DNS is managed at your domain registrar, **not** via GCP Cloud DNS. You create a single A record pointing your domain at the static IP output by Terraform.

| Record Type | Name | Value |
|-------------|------|-------|
| A | Your subdomain (e.g., `vault`) | Static IP from `terraform output instance_ip` |

### Artifact Registry

| Resource | Configuration |
|----------|---------------|
| **Repository** | `obsidian-palace` (Docker format) |
| **Cleanup** | Keeps the 5 most recent tagged images |

## Post-Deploy Health Check

The root module includes a `check {}` block that validates the service is reachable after deployment:

```hcl
check "health" {
  data "http" "health" {
    url = "https://YOUR_DOMAIN/health"
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

The GCE instance runs a startup script (COS-compatible -- no `apt-get`) that:

1. **Mounts the persistent disk** at `/mnt/disks/data` (formats on first boot)
2. **Creates data directories** (`vault`, `chromadb`, `chroma-cache`, `obsidian-config`, `letsencrypt`, `certbot-webroot`, `state`)
3. **Pulls secrets** from Secret Manager via the `gcloud` Docker image (COS has no gcloud on the host)
4. **Runs certbot in Docker** for Let's Encrypt SSL (first boot only)
5. **Symlinks certificates** to a stable path the container's nginx config expects
6. **Configures Docker auth** for Artifact Registry (writes config to the data disk since COS root is read-only)
7. **Pulls and starts** the Docker container with all env vars and volume mounts
8. **Schedules SSL cert renewal** — writes `certbot-renew.sh` to the data disk and installs a persistent systemd timer (twice-monthly at 3 AM UTC)

Inside the container, `entrypoint.sh` runs before supervisord:

1. **Symlinks `~/.obsidian-headless/`** → `/data/obsidian-config/headless/` (persists `ob login` auth token)
2. **Symlinks `~/.config/obsidian-headless/`** → `/data/obsidian-config/config/` (persists `ob sync-setup` vault config)
3. **Migrates legacy auth_token** from old paths if present
4. **Symlinks `~/.cache/chroma`** → `/data/chroma-cache/` (persists the ~79MB ONNX embedding model across deploys)
5. **Execs supervisord** which starts nginx, `sync-guard.sh` (→ `ob sync`), and the Python MCP server
