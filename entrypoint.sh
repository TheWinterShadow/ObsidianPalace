#!/bin/bash
# ObsidianPalace container entrypoint.
# 1. Links persisted Obsidian Sync credentials from the data disk.
# 2. Ensures data directories exist.
# 3. Execs supervisord to manage all processes.
#
# Sync safety checks (credentials, config, vault file count) are handled
# by sync-guard.sh, which supervisord calls instead of ob sync directly.

set -euo pipefail

log() { echo "[entrypoint] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

# --- Link Obsidian Sync credentials ---
# ob CLI expects ~/.obsidian-headless/auth_token. The auth_token is persisted
# on the data disk at /data/obsidian-config/ (survives container restarts).
# Initial setup requires a one-time manual `ob login` inside the container.
OBSIDIAN_CONFIG_DIR="/root/.obsidian-headless"
PERSISTED_CONFIG="/data/obsidian-config"

mkdir -p "$PERSISTED_CONFIG"
ln -sfn "$PERSISTED_CONFIG" "$OBSIDIAN_CONFIG_DIR"

if [ -f "$PERSISTED_CONFIG/auth_token" ]; then
    log "Obsidian Sync credentials linked from $PERSISTED_CONFIG"
else
    log "WARNING: No auth_token found — sync-guard.sh will block ob sync"
    log "Run 'docker exec -it obsidian-palace ob login' to authenticate"
fi

# --- Ensure data directories exist ---
mkdir -p /data/vault /data/chromadb

# --- Create sync-readiness flag path ---
# sync-guard.sh + ob sync will run via supervisord. This background watcher
# creates a marker file once .md files exist in the vault, signaling that the
# MCP server can serve content. Times out and proceeds anyway so the server
# always starts (it can still serve from whatever is on disk).
SYNC_READY_FLAG="/tmp/obsidian-sync-ready"
rm -f "$SYNC_READY_FLAG"

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
    touch "$SYNC_READY_FLAG"
    log "WARNING: Sync readiness timed out after ${TIMEOUT}s — proceeding anyway"
) &

log "Starting supervisord"
exec supervisord -n -c /etc/supervisor/supervisord.conf
