---
title: Troubleshooting
description: Diagnose and fix common ObsidianPalace deployment issues.
icon: material/bug-outline
---

# Troubleshooting

All troubleshooting starts by SSHing into the GCE instance:

```bash
gcloud compute ssh obsidian-palace --zone=us-central1-a --project=YOUR_PROJECT_ID
```

!!! info "Container-Optimized OS (COS)"
    The GCE instance runs COS, which has a **read-only root filesystem**. You cannot install packages with `apt`, write to `/etc`, or modify system files. All mutable state lives on the persistent disk at `/mnt/disks/data/`. Docker is the only way to run software. Keep this in mind for all troubleshooting steps below.

---

## General diagnostics

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

## SSL certificate not issued

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

## Obsidian Sync: `ob` CLI troubleshooting

The `ob` CLI (obsidian-headless) is the Node.js sidecar that syncs your vault. Most sync issues trace back to auth tokens or sync configuration.

### Verify auth token

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

### Verify sync configuration

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

### Run sync manually

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

### Sync config lost after container rebuild

When the container image is rebuilt and redeployed, the `ob` CLI's runtime config inside the container is replaced. The auth token survives because it's on the persistent disk, but the sync config at `/data/vault/.obsidian/` should also survive since it's on the data disk.

If sync breaks after a deploy:

1. Check that `/data/vault/.obsidian/` still has content
2. If empty, re-run `ob sync-setup` (you don't need to re-run `ob login` unless the token also expired)
3. Restart the container: `docker restart obsidian-palace`

---

## Server starts but doesn't respond to requests

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

## Slow cold starts (ONNX model download)

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

## MCP client connection issues

### Wrong transport endpoint

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

### OAuth discovery chain

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

### OAuth discovery returns `localhost`

**Symptom**: MCP clients fail to connect. `curl https://YOUR_DOMAIN/.well-known/oauth-protected-resource` returns URLs pointing to `https://localhost:8080/` instead of your public domain.

**Cause**: The `OBSIDIAN_PALACE_SERVER_URL` environment variable is not set or not being passed to the container. The server defaults to `https://localhost:8080`.

**Fix**: Ensure the docker run command includes `-e OBSIDIAN_PALACE_SERVER_URL="https://YOUR_DOMAIN"`. In the Terraform-managed startup script, this is set automatically from `var.domain`. Verify the `domain` variable is set in your TFC workspace.

```bash
# Check what the container sees
docker exec obsidian-palace env | grep SERVER_URL
# Expected: OBSIDIAN_PALACE_SERVER_URL=https://YOUR_DOMAIN
```

### OAuth token issues

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

## Container not starting

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

### Re-run the startup script

The COS startup script handles pulling the image, injecting secrets, and starting the container. If something went wrong during boot, you can re-run it:

```bash
sudo google_metadata_script_runner startup
```

This is safe to re-run -- it's idempotent. It will stop the existing container (if any), pull the latest image, and start a new container.

---

## Persistent disk issues

### Verify disk is mounted

```bash
mount | grep /mnt/disks/data
# Should show: /dev/sdb on /mnt/disks/data type ext4 (rw,relatime)

ls /mnt/disks/data/
# Expected directories: vault/ chromadb/ obsidian-config/ letsencrypt/ certbot-webroot/ docker-config/ state/
```

If the disk isn't mounted, the startup script should handle it. Re-run:

```bash
sudo google_metadata_script_runner startup
```

### Check data integrity after instance reset

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

## ChromaDB out of memory

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
