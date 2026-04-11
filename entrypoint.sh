#!/bin/bash
# ObsidianPalace container entrypoint.
# 1. Links persisted Obsidian Sync credentials from the data disk.
# 2. Waits for initial vault sync to complete before starting the MCP server.
# 3. Execs supervisord to manage all processes.

set -euo pipefail

log() { echo "[entrypoint] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

# --- Link Obsidian Sync credentials ---
# ob CLI expects ~/.obsidian-headless/auth_token. The auth_token is persisted
# on the data disk at /data/obsidian-config/ (survives container restarts).
# Initial setup requires a one-time manual `ob login` inside the container.
OBSIDIAN_CONFIG_DIR="/root/.obsidian-headless"
PERSISTED_CONFIG="/data/obsidian-config"

if [ -f "$PERSISTED_CONFIG/auth_token" ]; then
    # Symlink the whole directory so ob reads/writes to the persistent disk.
    ln -sfn "$PERSISTED_CONFIG" "$OBSIDIAN_CONFIG_DIR"
    log "Obsidian Sync credentials linked from $PERSISTED_CONFIG"
else
    mkdir -p "$PERSISTED_CONFIG"
    ln -sfn "$PERSISTED_CONFIG" "$OBSIDIAN_CONFIG_DIR"
    log "WARNING: No auth_token found at $PERSISTED_CONFIG/auth_token"
    log "Run 'docker exec -it obsidian-palace ob login' to authenticate"
fi

# --- Ensure data directories exist ---
mkdir -p /data/vault /data/chromadb

# --- One-time sync setup check ---
# ob sync-setup writes config to /data/vault/.obsidian/. If it exists, sync is
# already configured. If not, log instructions for manual setup.
if [ -d "/data/vault/.obsidian" ] && [ -n "$(ls -A /data/vault/.obsidian/ 2>/dev/null)" ]; then
    log "Vault sync already configured at /data/vault"
else
    log "WARNING: Vault sync not configured"
    log "Run: docker exec obsidian-palace ob sync-setup --vault <VAULT_ID> --path /data/vault --device-name obsidian-palace"
fi

# --- Create sync-readiness flag path ---
# supervisord starts ob sync; this script creates a marker file once the initial
# sync pulls at least one file. The MCP server's lifespan waits for this marker.
SYNC_READY_FLAG="/tmp/obsidian-sync-ready"
rm -f "$SYNC_READY_FLAG"

# --- Start a background watcher that creates the readiness flag ---
# Wait up to 120s for at least one .md file to appear in the vault.
# If ob sync isn't configured or the vault is empty, time out and proceed anyway.
(
    TIMEOUT=120
    ELAPSED=0
    while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
        if find /data/vault -name "*.md" -print -quit 2>/dev/null | grep -q .; then
            touch "$SYNC_READY_FLAG"
            log "Vault sync ready — .md files detected"
            exit 0
        fi
        sleep 2
        ELAPSED=$((ELAPSED + 2))
    done
    # Timed out — create the flag anyway so the server starts.
    touch "$SYNC_READY_FLAG"
    log "WARNING: Sync readiness timed out after ${TIMEOUT}s — proceeding anyway"
) &

log "Starting supervisord"
exec supervisord -n -c /etc/supervisor/conf.d/obsidian-palace.conf
