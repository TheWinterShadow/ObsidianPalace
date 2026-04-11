---
title: Setup Guide
description: Deploy your own ObsidianPalace instance from scratch.
icon: material/clipboard-check-outline
---

# Setup Guide

This guide walks you through deploying your own ObsidianPalace instance. By the end, you'll have a running MCP server that gives Claude (and any MCP client) full read/write/search access to your Obsidian vault.

**Time estimate**: 45--60 minutes for a first-time setup.

**Monthly cost**: ~$15 (GCE e2-small + persistent disk + static IP).

---

## Prerequisites

Before you begin, make sure you have the following:

| Requirement | Why |
|-------------|-----|
| A [GCP account](https://cloud.google.com/) with billing enabled | Hosts the VM, secrets, and container registry |
| [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5 | Provisions all infrastructure |
| A [Terraform Cloud](https://app.terraform.io/) account (free tier) | Stores Terraform state and runs applies |
| [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`) | Authenticates Docker pushes and SSH access |
| [Docker](https://docs.docker.com/get-docker/) | Builds the container image |
| [Node.js](https://nodejs.org/) >= 18 | Required to run `ob login` locally |
| An [Obsidian Sync](https://obsidian.md/sync) subscription | Keeps the vault in sync between your apps and the server |
| A domain name you control | For HTTPS and OAuth redirect URIs |
| A Google account (Gmail or Workspace) | Used for OAuth authentication -- this is the account that will be allowed access |
| An [Anthropic API key](https://console.anthropic.com/) | Powers AI-assisted note placement (optional but recommended) |

---

## Step 1: Create a GCP Project

Create a new GCP project dedicated to ObsidianPalace. Using a separate project keeps billing, IAM, and resources isolated.

```bash
gcloud projects create YOUR_PROJECT_ID --name="ObsidianPalace"
gcloud config set project YOUR_PROJECT_ID

# Link a billing account
gcloud billing accounts list
gcloud billing projects link YOUR_PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

!!! tip "Project ID"
    Pick a globally unique project ID (e.g., `obsidianpalace-yourname`). You'll reference it throughout this guide as `YOUR_PROJECT_ID`.

---

## Step 2: Create a Google OAuth 2.0 Client

ObsidianPalace uses Google OAuth to authenticate MCP clients. You need a **Web application** OAuth client.

1. Go to the [Google Cloud Console > APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **Create Credentials** > **OAuth client ID**
3. If prompted, configure the **OAuth consent screen** first:
    - User Type: **External** (or Internal if using Workspace)
    - App name: `ObsidianPalace`
    - Scopes: just `email` and `profile` (defaults)
    - Add your email as a test user
4. Back on the credentials page, create the client:
    - Application type: **Web application**
    - Name: `ObsidianPalace`
    - Authorized redirect URIs: `https://YOUR_DOMAIN/oauth2/callback`

Save the **Client ID** and **Client Secret** -- you'll need them in Step 5.

!!! warning "Web application, not Desktop"
    The OAuth client type **must** be "Web application." Desktop clients don't support redirect URIs, which the MCP OAuth 2.1 flow requires.

---

## Step 3: Get Obsidian Sync Credentials

The `ob login` command is interactive and must be run once on your local machine. It authenticates with your Obsidian account and saves a session token.

```bash
# Install obsidian-headless
npm install -g obsidian-headless

# Login (interactive — enter your Obsidian account email, password, and MFA code)
ob login
```

After login, the CLI writes an auth token to `~/.obsidian-headless/auth_token`. This file is what the server uses to sync your vault.

!!! note "MFA required"
    If your Obsidian account has MFA enabled (it should), `ob login` will prompt for the code. This step cannot be automated.

### Find your vault ID

You'll need your vault ID to configure sync on the server later (Step 8). List your vaults:

```bash
ob list-vaults
```

Note the vault ID (a 32-character hex string like `a4a2ccb7cd82d034751c55ad5e38c4a3`) for the vault you want to sync.

---

## Step 4: Fork and Configure the Repository

```bash
# Clone the repository
git clone https://github.com/TheWinterShadow/ObsidianPalace.git
cd ObsidianPalace
```

### Terraform configuration

The Terraform code needs a few changes for your deployment:

**1. Update `terraform/environments/prod/versions.tf`** -- replace the Terraform Cloud org and workspace with yours:

```hcl title="terraform/environments/prod/versions.tf"
terraform {
  cloud {
    organization = "YOUR_TFC_ORG"

    workspaces {
      name = "obsidian-palace"  # or whatever you prefer
    }
  }

  # ... providers stay the same
}
```

**2. Update `terraform/environments/prod/variables.tf`** -- change the default project ID:

```hcl title="terraform/environments/prod/variables.tf"
variable "project_id" {
  description = "GCP project ID."
  type        = string
  default     = "YOUR_PROJECT_ID"
}
```

**3. Update `terraform/environments/prod/main.tf`** -- set your domain and remove the hardcoded health check URL:

```hcl title="terraform/environments/prod/main.tf"
module "obsidian_palace" {
  source = "../../modules/obsidian_palace"

  # ... other variables
  domain = "YOUR_DOMAIN"  # e.g., "vault.yourdomain.com"
}

check "health" {
  data "http" "health" {
    url = "https://YOUR_DOMAIN/health"
    # ...
  }
}
```

### CI/CD configuration (optional)

If you want automated builds and deploys via GitHub Actions, update `.github/workflows/ci.yml` and `.github/workflows/deploy.yml`:

- Change `GCP_PROJECT_ID` to your project ID
- Set up [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) between GitHub Actions and your GCP project
- Create the required GitHub secrets: `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `TFC_API_TOKEN`, `TFC_WORKSPACE_ID`

If you prefer manual deploys, you can skip CI/CD entirely and build/push the image manually (covered in Step 7).

---

## Step 5: Set Up Terraform Cloud

1. Create an account at [app.terraform.io](https://app.terraform.io/) (free tier is fine)
2. Create an **organization** (or use an existing one)
3. Create a **workspace** named `obsidian-palace` (or matching what you set in `versions.tf`)
    - Execution mode: **API-driven** (not VCS-driven -- the GitHub Actions workflow handles triggering)
4. Set these **workspace variables**:

### Required variables

| Variable | Category | Sensitive | Value |
|----------|----------|-----------|-------|
| `container_image` | Terraform | No | `us-central1-docker.pkg.dev/YOUR_PROJECT_ID/obsidian-palace/obsidian-palace:latest` |
| `google_oauth_client_id` | Terraform | Yes | From Step 2 |
| `google_oauth_client_secret` | Terraform | Yes | From Step 2 |
| `allowed_email` | Terraform | Yes | Your Google account email |
| `anthropic_api_key` | Terraform | Yes | Your Anthropic API key |

### Optional variables

| Variable | Default | Description |
|----------|---------|-------------|
| `allowed_ssh_cidrs` | `[]` | CIDR blocks for SSH access (e.g., `["203.0.113.1/32"]`) |
| `allowed_https_cidrs` | `[]` | Additional HTTPS restrictions (empty = allow all, rely on OAuth) |

---

## Step 6: Deploy Infrastructure

```bash
cd terraform/environments/prod

# Initialize Terraform (connects to Terraform Cloud)
terraform init

# Preview what will be created
terraform plan

# Deploy everything
terraform apply
```

This creates:

- GCE e2-small instance with Container-Optimized OS
- 20 GB persistent disk for vault data + ChromaDB index
- Static external IP address
- Firewall rules (HTTP/HTTPS)
- Artifact Registry repository for Docker images
- Secret Manager secrets (OAuth creds, API keys)
- Service account with minimal IAM permissions

After apply completes, note the outputs:

```bash
terraform output instance_ip          # Your server's IP address
terraform output artifact_registry_url # Where to push Docker images
```

---

## Step 7: Build and Push the Docker Image

```bash
# Authenticate Docker to your Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build the image
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT_ID/obsidian-palace/obsidian-palace:latest .

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/YOUR_PROJECT_ID/obsidian-palace/obsidian-palace:latest
```

Then reset the VM to pick up the new image:

```bash
gcloud compute instances reset obsidian-palace \
  --zone=us-central1-a \
  --project=YOUR_PROJECT_ID
```

!!! tip "Automated builds"
    If you set up CI/CD (Step 4), pushing to `main` will automatically build, push, and deploy the image. You only need to do this manual step once for the initial deployment.

---

## Step 8: Configure DNS

Point your domain at the static IP from `terraform output instance_ip`.

At your domain registrar (or DNS provider), create an **A record**:

| Type | Name | Value |
|------|------|-------|
| A | `vault` (or your subdomain) | `YOUR_STATIC_IP` |

!!! note "DNS propagation"
    DNS changes can take minutes to hours to propagate. You can verify with `dig YOUR_DOMAIN` or `nslookup YOUR_DOMAIN`.

The startup script automatically obtains a Let's Encrypt SSL certificate via certbot on first boot. If the certificate isn't ready yet (DNS hasn't propagated), SSH into the instance and re-run the startup script:

```bash
gcloud compute ssh obsidian-palace --zone=us-central1-a --project=YOUR_PROJECT_ID
# Once connected:
sudo google_metadata_script_runner startup
```

---

## Step 9: Configure Obsidian Sync on the Server

The vault sync requires a one-time interactive setup inside the running container. SSH into the instance and run `ob login` + `ob sync-setup` inside the container:

```bash
# SSH into the GCE instance
gcloud compute ssh obsidian-palace --zone=us-central1-a --project=YOUR_PROJECT_ID

# Exec into the running container
docker exec -it obsidian-palace bash

# Inside the container: authenticate with Obsidian
ob login

# Set up vault sync (use the vault ID from Step 3)
ob sync-setup \
  --vault YOUR_VAULT_ID \
  --path /data/vault \
  --device-name obsidian-palace

# Exit the container and restart it to start syncing
exit
docker restart obsidian-palace
```

The auth token is persisted on the data disk at `/data/obsidian-config/auth_token`, so it survives container restarts. You only need to do this once (unless the token expires or you rebuild the persistent disk).

!!! warning "Container rebuilds"
    If the container is rebuilt (not just restarted), the `ob login` session inside the container may be lost. The entrypoint script symlinks from the persistent disk, but if you delete the data disk or re-create the instance from scratch, you'll need to repeat this step.

---

## Step 10: Verify the Deployment

### Health check

```bash
curl https://YOUR_DOMAIN/health
# Expected: {"status":"ok","version":"0.1.0"}
```

### MCP OAuth discovery

```bash
# Protected resource metadata
curl https://YOUR_DOMAIN/.well-known/oauth-protected-resource

# Authorization server metadata
curl https://YOUR_DOMAIN/.well-known/oauth-authorization-server
```

Both should return JSON with OAuth endpoints. If these work, the MCP OAuth 2.1 flow is ready.

### API docs

- **Swagger UI**: `https://YOUR_DOMAIN/docs`
- **ReDoc**: `https://YOUR_DOMAIN/redoc`

---

## Step 11: Connect an MCP Client

### Claude Code

Add the server to your Claude Code MCP configuration:

```bash
claude mcp add obsidian-palace --transport sse https://YOUR_DOMAIN/sse
```

Claude Code will automatically:

1. Discover the OAuth metadata endpoints
2. Dynamically register as an OAuth client
3. Open your browser for Google login
4. Exchange tokens and connect to the SSE stream

After authenticating, you should see the five ObsidianPalace tools available in Claude Code.

### Claude Desktop

Add to your Claude Desktop MCP config file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json title="claude_desktop_config.json"
{
  "mcpServers": {
    "obsidian-palace": {
      "transport": "sse",
      "url": "https://YOUR_DOMAIN/sse"
    }
  }
}
```

Restart Claude Desktop. It will prompt you to authenticate via Google OAuth on first connection.

### Other MCP clients

Any MCP client that supports SSE transport and OAuth 2.1 (with dynamic client registration + PKCE) can connect. The SSE endpoint is:

```
https://YOUR_DOMAIN/sse
```

---

## Troubleshooting

All troubleshooting starts by SSHing into the GCE instance:

```bash
gcloud compute ssh obsidian-palace --zone=us-central1-a --project=YOUR_PROJECT_ID
```

!!! info "Container-Optimized OS (COS)"
    The GCE instance runs COS, which has a **read-only root filesystem**. You cannot install packages with `apt`, write to `/etc`, or modify system files. All mutable state lives on the persistent disk at `/mnt/disks/data/`. Docker is the only way to run software. Keep this in mind for all troubleshooting steps below.

---

### General diagnostics

Run these first to understand the current state:

```bash
# Container running?
docker ps -a

# All three processes healthy?
docker exec obsidian-palace supervisorctl status
# Expected:
#   mcp-server       RUNNING   pid 42, uptime 1:23:45
#   nginx            RUNNING   pid 12, uptime 1:23:45
#   obsidian-sync    RUNNING   pid 37, uptime 1:23:45

# Recent container logs (all processes interleaved)
docker logs obsidian-palace --tail 200

# Per-process logs via supervisord
docker exec obsidian-palace supervisorctl tail -f mcp-server
docker exec obsidian-palace supervisorctl tail -f obsidian-sync
docker exec obsidian-palace supervisorctl tail -f nginx

# Persistent disk mounted?
mount | grep /mnt/disks/data
ls /mnt/disks/data/
# Expected: vault/ chromadb/ obsidian-config/ letsencrypt/ certbot-webroot/ docker-config/

# Health check from inside the instance (bypasses nginx/SSL)
curl http://localhost:8080/health
```

!!! note "`supervisorctl` socket issues"
    If `supervisorctl status` returns a socket connection error, the supervisord unix socket may not be configured. You can still check process status with `docker exec obsidian-palace ps aux` and view logs with `docker logs`.

---

### SSL certificate not issued

If `curl https://YOUR_DOMAIN/health` fails with a certificate error, certbot may not have run successfully.

```bash
# Check if certs exist
ls /mnt/disks/data/letsencrypt/live/

# Re-run certbot manually if needed (stop the container first to free port 80)
docker stop obsidian-palace
docker run --rm \
  -v /mnt/disks/data/letsencrypt:/etc/letsencrypt \
  -v /mnt/disks/data/certbot-webroot:/var/www/certbot \
  -p 80:80 \
  certbot/certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email your-email@gmail.com \
    -d YOUR_DOMAIN
docker start obsidian-palace
```

**Common causes:**

- DNS not propagated yet -- verify with `dig YOUR_DOMAIN` that it resolves to your static IP
- Port 80 blocked -- the firewall rule must allow HTTP for certbot's challenge
- Certbot rate limits -- Let's Encrypt allows ~5 certificates per domain per week

---

### Obsidian Sync: `ob` CLI troubleshooting

The `ob` CLI (obsidian-headless) is the Node.js sidecar that syncs your vault. Most sync issues trace back to auth tokens or sync configuration.

#### Verify auth token

```bash
# Check the symlink and auth token on the persistent disk
docker exec obsidian-palace ls -la /root/.obsidian-headless/
# Should be a symlink to /data/obsidian-config/

docker exec obsidian-palace cat /root/.obsidian-headless/auth_token
# Should be a 32-byte hex string
```

If the auth token is missing or the symlink is broken, re-authenticate:

```bash
docker exec -it obsidian-palace ob login
# Enter: email, password, MFA code (interactive)
```

The entrypoint script symlinks `/root/.obsidian-headless/` → `/data/obsidian-config/` on startup, so the token persists on the data disk across container restarts.

#### Verify sync configuration

`ob sync-setup` writes config to `/data/vault/.obsidian/`. If this directory is empty or missing, sync won't work even if the auth token is valid.

```bash
# Check if sync config exists
docker exec obsidian-palace ls -la /data/vault/.obsidian/
# Should contain files like sync-config.json, etc.

# List available vaults (to find or verify your vault ID)
docker exec obsidian-palace ob list-vaults
# Output: vault ID (32-char hex), name, region
```

If sync config is missing, re-run setup:

```bash
docker exec obsidian-palace ob sync-setup \
  --vault YOUR_VAULT_ID \
  --path /data/vault \
  --device-name obsidian-palace
```

!!! warning "Vault ID"
    The vault ID is a 32-character hex string (e.g., `a4a2ccb7cd82d034751c55ad5e38c4a3`), NOT the vault name. Use `ob list-vaults` to find it.

#### Run sync manually

If `ob sync --continuous` is failing in supervisord, run it manually to see the error output in real time:

```bash
# Stop the supervised sync process
docker exec obsidian-palace supervisorctl stop obsidian-sync

# Run sync manually in the foreground
docker exec -it obsidian-palace ob sync --continuous --path /data/vault

# Once diagnosed, restart the supervised process
docker exec obsidian-palace supervisorctl start obsidian-sync
```

**Common sync errors:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| `auth_token not found` | Token missing or symlink broken | Re-run `ob login` |
| `vault not found` | Sync not configured | Re-run `ob sync-setup` |
| `network error` / `ECONNREFUSED` | Obsidian Sync servers unreachable | Check instance egress; try again later |
| Sync starts but no files appear | Wrong vault ID or empty vault | Verify vault ID with `ob list-vaults` |
| `FATAL` on startup, immediate exit | Auth token expired | Re-run `ob login` (tokens expire after extended periods) |

#### Sync config lost after container rebuild

When the container image is rebuilt and redeployed, the `ob` CLI's runtime config inside the container is replaced. The auth token survives because it's on the persistent disk, but the sync config at `/data/vault/.obsidian/` should also survive since it's on the data disk.

If sync breaks after a deploy:

1. Check that `/data/vault/.obsidian/` still has content
2. If empty, re-run `ob sync-setup` (you don't need to re-run `ob login` unless the token also expired)
3. Restart the container: `docker restart obsidian-palace`

---

### Server starts but doesn't respond to requests

**Symptom**: Container is running, `docker ps` shows it as healthy, but `curl https://YOUR_DOMAIN/health` hangs or times out.

**Likely cause**: Vault indexing blocking the server startup. This was a bug in early versions where `index_vault()` ran during the FastAPI lifespan startup, blocking uvicorn from serving requests. On e2-small with a 600MB vault, indexing can take several minutes.

**Current behavior**: Indexing now runs as a background `asyncio.create_task()`. The server starts immediately and search returns empty results until indexing completes. If you're seeing this issue, make sure you're on the latest image.

**Diagnosis**:

```bash
# Check if uvicorn is even listening
docker exec obsidian-palace curl -s http://localhost:8080/health

# Check MCP server logs for indexing progress
docker exec obsidian-palace supervisorctl tail -f mcp-server
# Look for: "Vault indexing started in background"
# Then later: "Background vault indexing complete: N files, M drawers"

# Check memory usage (indexing + ChromaDB can spike)
docker exec obsidian-palace cat /proc/meminfo | head -5
```

---

### Slow cold starts (ONNX model download)

**Symptom**: First startup after a fresh container deploy takes 2-5 extra minutes. Subsequent restarts are fast.

**Cause**: MemPalace/ChromaDB uses an ONNX embedding model (~79MB) that is downloaded from the internet on first use. This happens inside `index_vault()` during the background indexing task.

**Workaround**: The model is cached in ChromaDB's data directory (`/data/chromadb/`), which lives on the persistent disk. Once downloaded, it persists across container restarts. However, if you delete the ChromaDB directory or recreate the persistent disk, the model will be re-downloaded.

```bash
# Verify the model is cached
docker exec obsidian-palace ls -la /data/chromadb/
# Look for onnx_models/ or similar cache directory
```

!!! tip "Future optimization"
    A future improvement would be to bake the ONNX model into the Docker image or download it during the image build step. This eliminates the cold-start penalty entirely.

---

### MCP client connection issues

#### Wrong transport endpoint

Different MCP clients use different transports:

| Client | Transport | Endpoint |
|--------|-----------|----------|
| Claude Desktop | SSE | `https://YOUR_DOMAIN/sse` |
| Claude Code | SSE | `https://YOUR_DOMAIN/sse` |
| Claude iOS / claude.ai | SSE | `https://YOUR_DOMAIN/sse` |
| OpenCode | Streamable HTTP | `https://YOUR_DOMAIN/mcp` |

**Common mistake**: Configuring OpenCode with the SSE endpoint (`/sse`). OpenCode uses Streamable HTTP (POST to a single endpoint), so it sends a POST to `/sse` which returns `405 Method Not Allowed`. Fix: point OpenCode at `/mcp`.

```json title="~/.config/opencode/opencode.json"
{
  "mcp": {
    "obsidian-palace": {
      "type": "remote",
      "url": "https://YOUR_DOMAIN/mcp"
    }
  }
}
```

#### OAuth discovery chain

MCP clients follow a specific OAuth discovery sequence. If any step fails, the client won't connect. You can verify each step manually:

```bash
# 1. Unauthenticated request should return 401 with WWW-Authenticate header
curl -sI https://YOUR_DOMAIN/sse
# Look for: WWW-Authenticate: Bearer resource_metadata="..."

# 2. Protected resource metadata
curl -s https://YOUR_DOMAIN/.well-known/oauth-protected-resource | python3 -m json.tool

# 3. Authorization server metadata
curl -s https://YOUR_DOMAIN/.well-known/oauth-authorization-server | python3 -m json.tool

# 4. Dynamic client registration (should accept POST)
curl -s -X POST https://YOUR_DOMAIN/register \
  -H "Content-Type: application/json" \
  -d '{"redirect_uris": ["http://localhost:9999/callback"], "client_name": "test"}'
```

If any of these return errors, check the MCP server logs.

#### OAuth token issues

**Symptom**: Auth flow completes (browser redirects back) but the MCP client gets 401 on subsequent requests.

**Known bug (fixed)**: In Python, `if token.expires_at and ...` skips validation when `expires_at=0` because `0` is falsy. The fix is `if token.expires_at is not None and ...`. If you're seeing this, make sure you're on the latest image.

**Diagnosis**:

```bash
# Check server logs during the auth flow
docker exec obsidian-palace supervisorctl tail -500 mcp-server | grep -i "token\|auth\|oauth"
```

**Other OAuth issues**:

- **Redirect URI mismatch**: The Google OAuth client's redirect URI must be exactly `https://YOUR_DOMAIN/oauth2/callback`. No trailing slash, no port number.
- **Test user not added**: While the OAuth consent screen is in "Testing" status, only explicitly added test users can authenticate. Go to Google Cloud Console > APIs & Services > OAuth consent screen > Test users.
- **Wrong client type**: The OAuth client must be "Web application," not "Desktop." Desktop clients don't support redirect URIs.

---

### Container not starting

```bash
# Check container status and exit code
docker ps -a
# Look at the STATUS column — if it says "Exited (1)", check logs

# Container logs (includes entrypoint + supervisord output)
docker logs obsidian-palace --tail 200

# Startup script logs (COS metadata script runner)
sudo journalctl -u google-startup-scripts.service --no-pager | tail -100
```

**Common causes:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container never starts | Image pull failed (Artifact Registry auth) | Check `docker pull` manually; verify service account has `artifactregistry.reader` |
| Exits immediately | Missing environment variables | Check startup script injects secrets from Secret Manager |
| Exits after a few seconds | supervisord config error | Check `docker logs` for supervisord parse errors |
| Running but no ports exposed | Docker run missing `-p` flags | Check the startup script's `docker run` command in instance metadata |

#### Re-run the startup script

The COS startup script handles pulling the image, injecting secrets, and starting the container. If something went wrong during boot, you can re-run it:

```bash
sudo google_metadata_script_runner startup
```

This is safe to re-run — it's idempotent. It will stop the existing container (if any), pull the latest image, and start a new container.

---

### Persistent disk issues

#### Verify disk is mounted

```bash
mount | grep /mnt/disks/data
# Should show: /dev/sdb on /mnt/disks/data type ext4 (rw,relatime)

ls /mnt/disks/data/
# Expected directories: vault/ chromadb/ obsidian-config/ letsencrypt/ certbot-webroot/ docker-config/
```

If the disk isn't mounted, the startup script should handle it. Re-run:

```bash
sudo google_metadata_script_runner startup
```

#### Check data integrity after instance reset

After a `gcloud compute instances reset`, the persistent disk is reattached but the mount may need to be re-established. Verify:

```bash
# Check disk is attached
lsblk
# Should show sdb (or similar) with the correct size

# Check mount
mount | grep /mnt/disks/data

# If not mounted, mount it manually
sudo mkdir -p /mnt/disks/data
sudo mount /dev/sdb /mnt/disks/data

# Then restart the container
sudo google_metadata_script_runner startup
```

---

### ChromaDB out of memory

The e2-small instance has 2 GB RAM. With a 600MB vault, the Python server + ChromaDB + ONNX embeddings + Node.js sync process typically uses 1.2-1.6 GB. If your vault is significantly larger (>1 GB of markdown), you may hit OOM.

**Diagnosis**:

```bash
# Check memory usage
free -h
docker stats obsidian-palace --no-stream

# Check if OOM killer fired
dmesg | grep -i "out of memory\|oom"
```

**Fix**: Upgrade to e2-medium (4 GB RAM). Set the `machine_type` Terraform variable:

```hcl
variable "machine_type" {
  default = "e2-medium"  # 4 GB RAM, ~$26/mo
}
```

Alternatively, disable MemPalace indexing to save memory (you lose semantic search):

```bash
# Set in Terraform or directly as an env var
OBSIDIAN_PALACE_MEMPALACE_ENABLED=false
```

---

## Configuration Reference

All configuration is via environment variables with the `OBSIDIAN_PALACE_` prefix. In production, these are injected by the startup script from Secret Manager. For local development, copy `.env.example` to `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSIDIAN_PALACE_GOOGLE_CLIENT_ID` | (required) | Google OAuth 2.0 client ID |
| `OBSIDIAN_PALACE_GOOGLE_CLIENT_SECRET` | (required) | Google OAuth 2.0 client secret |
| `OBSIDIAN_PALACE_ALLOWED_EMAIL` | (required) | Google account email allowed to access the server |
| `OBSIDIAN_PALACE_SERVER_URL` | `https://YOUR_URL` | Public URL of your server (used for OAuth metadata) |
| `OBSIDIAN_PALACE_VAULT_PATH` | `/data/vault` | Path to the Obsidian vault directory |
| `OBSIDIAN_PALACE_CHROMADB_PATH` | `/data/chromadb` | Path to the ChromaDB storage directory |
| `OBSIDIAN_PALACE_ANTHROPIC_API_KEY` | (empty) | Anthropic API key for AI placement |
| `OBSIDIAN_PALACE_MEMPALACE_ENABLED` | `true` | Enable/disable semantic search indexing |
| `OBSIDIAN_PALACE_HOST` | `0.0.0.0` | Server bind host |
| `OBSIDIAN_PALACE_PORT` | `8080` | Server bind port |
| `OBSIDIAN_PALACE_LOG_LEVEL` | `info` | Logging level |

!!! important "Set `SERVER_URL`"
    The `OBSIDIAN_PALACE_SERVER_URL` variable **must** match your public domain (e.g., `https://vault.yourdomain.com`). OAuth metadata endpoints use this value, and MCP clients will fail to connect if it doesn't match the actual URL.
