#!/bin/bash
# ObsidianPalace container entrypoint.
# 1. Copies Obsidian Sync credentials to the expected location.
# 2. Waits for initial vault sync to complete before starting the MCP server.
# 3. Execs supervisord to manage all processes.

set -euo pipefail

log() { echo "[entrypoint] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

# --- Copy Obsidian Sync credentials ---
# obsidian-headless expects ~/.obsidian-headless/auth_token (plain text string).
OBSIDIAN_CONFIG_DIR="/root/.obsidian-headless"
SYNC_CREDS_MOUNT="/data/obsidian-config/auth_token"

if [ -f "$SYNC_CREDS_MOUNT" ]; then
    mkdir -p "$OBSIDIAN_CONFIG_DIR"
    cp "$SYNC_CREDS_MOUNT" "$OBSIDIAN_CONFIG_DIR/auth_token"
    chmod 600 "$OBSIDIAN_CONFIG_DIR/auth_token"
    log "Obsidian Sync credentials installed to $OBSIDIAN_CONFIG_DIR/auth_token"
else
    log "WARNING: No Obsidian Sync credentials found at $SYNC_CREDS_MOUNT"
    log "ob sync will fail without credentials — vault sync disabled"
fi

# --- Ensure data directories exist ---
mkdir -p /data/vault /data/chromadb

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
