---
title: Operations
description: Day-to-day operations, CI/CD, updating, monitoring, and maintenance.
icon: material/rocket-launch
---

# Operations

This page covers day-to-day operations for a running ObsidianPalace instance. For initial setup, see the [Setup Guide](../setup/index.md).

---

## CI/CD Pipeline

ObsidianPalace uses two GitHub Actions workflows that run in sequence:

### CI (`ci.yml`)

Triggers on every push to `main` and on pull requests.

| Job | What it does |
|-----|-------------|
| **Lint** | Runs `ruff check` and `ruff format --check` |
| **Test** | Runs `pytest tests/ -v` |
| **Build & Push** | Builds the Docker image and pushes to Artifact Registry (main only) |

The image is tagged with both the short SHA (e.g., `a1b2c3d`) and `latest`.

### Deploy (`deploy.yml`)

Triggers after CI completes on `main`, or on direct pushes to `terraform/`.

1. Updates the `container_image` variable in Terraform Cloud to the new SHA tag
2. Uploads the Terraform configuration
3. Creates and applies a Terraform run
4. Resets the GCE instance to pick up the new image

### Required GitHub secrets

| Secret | Description |
|--------|-------------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity Federation provider resource name |
| `GCP_SERVICE_ACCOUNT` | GCP service account email for GitHub Actions |
| `TFC_API_TOKEN` | Terraform Cloud API token |
| `TFC_WORKSPACE_ID` | Terraform Cloud workspace ID |

### Setting up Workload Identity Federation

Follow the [GCP guide for GitHub Actions](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines#github-actions) to create a Workload Identity Pool and Provider. The service account needs:

- `roles/artifactregistry.writer` (push images)
- `roles/compute.instanceAdmin.v1` (reset instance)

---

## Manual Deployment

If you prefer not to use CI/CD, or need to deploy a hotfix:

```bash
# Build and push
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT_ID/obsidian-palace/obsidian-palace:latest .
gcloud auth configure-docker us-central1-docker.pkg.dev
docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/obsidian-palace/obsidian-palace:latest

# Reset the instance to pull the new image
gcloud compute instances reset obsidian-palace \
  --zone=us-central1-a \
  --project=YOUR_PROJECT_ID
```

The startup script on the VM automatically pulls the configured image and restarts the container.

---

## Monitoring

### Health check

```bash
curl https://YOUR_DOMAIN/health
# {"status":"ok","version":"0.1.0"}
```

### Container logs

```bash
# SSH into the instance
gcloud compute ssh obsidian-palace --zone=us-central1-a --project=YOUR_PROJECT_ID

# View all container logs
docker logs obsidian-palace --tail 100 -f

# View per-process logs via supervisord
docker exec obsidian-palace supervisorctl tail -f mcp-server
docker exec obsidian-palace supervisorctl tail -f obsidian-sync
docker exec obsidian-palace supervisorctl tail -f nginx
```

### Process status

```bash
docker exec obsidian-palace supervisorctl status
# Expected output:
# mcp-server       RUNNING   pid 42, uptime 1:23:45
# nginx            RUNNING   pid 12, uptime 1:23:45
# obsidian-sync    RUNNING   pid 37, uptime 1:23:45
```

---

## SSL Certificate Renewal

Let's Encrypt certificates expire every 90 days. The startup script writes a renewal script to the data disk, but you need to schedule it.

### Manual renewal

```bash
# SSH into the instance
gcloud compute ssh obsidian-palace --zone=us-central1-a --project=YOUR_PROJECT_ID

# Run the certbot renewal
bash /mnt/disks/data/certbot-renew.sh
```

### Automated renewal via cron

On Container-Optimized OS, the root filesystem is read-only. Use `systemd-run` to schedule a recurring timer:

```bash
# SSH into the instance, then:
sudo systemd-run --on-calendar="*-*-01,15 03:00:00" \
  --unit=certbot-renew \
  /bin/bash /mnt/disks/data/certbot-renew.sh
```

This runs certbot on the 1st and 15th of each month at 3 AM.

---

## Updating Obsidian Sync Credentials

If your Obsidian Sync session expires or you change your Obsidian account password:

```bash
# SSH into the instance
gcloud compute ssh obsidian-palace --zone=us-central1-a --project=YOUR_PROJECT_ID

# Re-authenticate inside the container
docker exec -it obsidian-palace ob login

# Restart the container to pick up new credentials
docker restart obsidian-palace
```

The new auth token is written to the persistent disk and survives container restarts.

---

## Terraform State

State is stored in Terraform Cloud (free tier). To inspect or modify:

```bash
cd terraform/environments/prod

# Show current state
terraform show

# Import an existing resource
terraform import 'module.obsidian_palace.google_compute_instance.obsidian_palace' \
  'projects/YOUR_PROJECT_ID/zones/us-central1-a/instances/obsidian-palace'
```

### Switching to GCS backend

If you prefer storing state in a GCS bucket instead of Terraform Cloud, uncomment the GCS backend in `backend.tf` and remove the `cloud {}` block from `versions.tf`:

```hcl title="backend.tf"
terraform {
  backend "gcs" {
    bucket = "your-tfstate-bucket"
    prefix = "obsidian_palace/state"
  }
}
```

---

## Backup and Recovery

### What's on the persistent disk

| Path | Contents | Recreatable? |
|------|----------|-------------|
| `/mnt/disks/data/vault/` | Your Obsidian vault files | Yes -- re-synced from Obsidian Sync |
| `/mnt/disks/data/chromadb/` | Semantic search index | Yes -- rebuilt on startup |
| `/mnt/disks/data/obsidian-config/` | `ob` CLI auth token | No -- requires `ob login` |
| `/mnt/disks/data/letsencrypt/` | SSL certificates | Yes -- re-issued by certbot |

### Creating a disk snapshot

```bash
gcloud compute disks snapshot obsidian-palace-data \
  --zone=us-central1-a \
  --project=YOUR_PROJECT_ID \
  --snapshot-names=obsidian-palace-backup-$(date +%Y%m%d)
```

### Recovery from snapshot

If the data disk is lost, create a new disk from the snapshot and attach it:

```bash
gcloud compute disks create obsidian-palace-data \
  --zone=us-central1-a \
  --source-snapshot=obsidian-palace-backup-YYYYMMDD \
  --project=YOUR_PROJECT_ID
```

Then run `terraform apply` to reconcile state.

---

## Cost Estimate

| Resource | Monthly Cost |
|----------|-------------|
| GCE e2-small (always-on) | ~$13.00 |
| Persistent disk (20 GB pd-standard) | ~$0.80 |
| Static IP (in use) | ~$0.00 |
| Secret Manager (4 secrets) | ~$0.00 |
| Artifact Registry (storage) | ~$0.10 |
| **Total** | **~$14.00** |

!!! tip "Cost optimization"
    If you don't need the server running 24/7, you can stop the instance when not in use. A stopped e2-small costs ~$0 for compute (you still pay for the disk and static IP).
