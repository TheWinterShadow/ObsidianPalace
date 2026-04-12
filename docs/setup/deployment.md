---
title: Deployment
description: Deploy ObsidianPalace infrastructure and configure all required services.
icon: material/rocket-launch-outline
---

# Deployment

This page covers Steps 1--10: creating all infrastructure, building/pushing the image, configuring DNS and Obsidian Sync, and verifying the deployment.

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

You'll need your vault ID to configure sync on the server later (Step 9). List your vaults:

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
| `domain` | Terraform | No | Your domain (e.g., `vault.yourdomain.com`) |

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

!!! warning "One-time manual step"
    This step **must** be done manually after the first deploy. The `ob login` and `ob sync-setup` commands are interactive and cannot be automated through CI/CD.

    After this initial setup, credentials and sync config are persisted on the data disk and survive all future container restarts and image deploys. You should never need to repeat this unless you recreate the persistent disk or your Obsidian auth token expires.

    Until this step is complete, the `obsidian-sync` process will be in `FATAL` state (sync-guard.sh blocks it), the vault directory will be empty, and search will return no results. The MCP server itself still runs and responds to health checks -- only sync is affected.

SSH into the instance and configure sync inside the running container:

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

### What gets persisted

The `entrypoint.sh` script symlinks two `ob` CLI directories to the persistent data disk:

| `ob` CLI writes to | Symlinked to (persistent disk) | Created by |
|---------------------|-------------------------------|------------|
| `~/.obsidian-headless/auth_token` | `/data/obsidian-config/headless/auth_token` | `ob login` |
| `~/.config/obsidian-headless/sync/<vault-id>/config.json` | `/data/obsidian-config/config/sync/<vault-id>/config.json` | `ob sync-setup` |

Both persist across container restarts, image rebuilds, and VM resets. The `entrypoint.sh` recreates the symlinks on every container start.

### sync-guard.sh safety gates

Before `ob sync` starts, `sync-guard.sh` checks three conditions:

1. **Auth token exists** -- verifies `/data/obsidian-config/headless/auth_token` is present
2. **Sync config exists** -- verifies at least one `config.json` exists under `/data/obsidian-config/config/sync/`
3. **Vault file count** -- counts `.md` files in `/data/vault` and blocks sync if below the safety threshold (default: 400)

The file count gate prevents a scenario where an empty or corrupted vault tells Obsidian Sync "I have no files," causing deletions to propagate to all connected devices (phones, desktops, etc.).

!!! tip "Adjusting the file count threshold"
    The default minimum is 400 `.md` files. If your vault is smaller, set the `OBSIDIAN_PALACE_MIN_VAULT_FILES` environment variable to an appropriate value. Set it close to your actual vault size for the best protection.

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
| `OBSIDIAN_PALACE_OAUTH_STATE_PATH` | `/data/oauth_state.json` | Path to the OAuth state persistence file |
| `OBSIDIAN_PALACE_ANTHROPIC_API_KEY` | (empty) | Anthropic API key for AI placement |
| `OBSIDIAN_PALACE_MEMPALACE_ENABLED` | `true` | Enable/disable semantic search indexing |
| `OBSIDIAN_PALACE_HOST` | `0.0.0.0` | Server bind host |
| `OBSIDIAN_PALACE_PORT` | `8080` | Server bind port |
| `OBSIDIAN_PALACE_LOG_LEVEL` | `info` | Logging level |

!!! important "Set `SERVER_URL`"
    The `OBSIDIAN_PALACE_SERVER_URL` variable **must** match your public domain (e.g., `https://vault.yourdomain.com`). OAuth metadata endpoints use this value, and MCP clients will fail to connect if it doesn't match the actual URL.
