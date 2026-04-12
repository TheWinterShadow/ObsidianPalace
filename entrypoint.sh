#!/bin/bash
# ObsidianPalace container entrypoint.
# 1. Links persisted Obsidian CLI state directories from the data disk.
# 2. Ensures data directories exist.
# 3. Execs supervisord to manage all processes.
#
# Sync safety checks (credentials, config, vault file count) are handled
# by sync-guard.sh, which supervisord calls instead of ob sync directly.

set -euo pipefail

log() { echo "[entrypoint] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

# --- Persist Obsidian CLI state directories ---
# The ob CLI uses TWO config directories:
#   ~/.obsidian-headless/auth_token    — written by `ob login`
#   ~/.config/obsidian-headless/       — written by `ob sync-setup` (vault config)
#
# Both live on ephemeral container filesystem by default. We symlink them to
# the persistent data disk so they survive container restarts and deploys.
PERSISTED_CONFIG="/data/obsidian-config"

# 1. ~/.obsidian-headless/ → /data/obsidian-config/headless/
mkdir -p "$PERSISTED_CONFIG/headless"
ln -sfn "$PERSISTED_CONFIG/headless" "/root/.obsidian-headless"

if [ -f "$PERSISTED_CONFIG/headless/auth_token" ]; then
    log "ob login credentials linked from $PERSISTED_CONFIG/headless/"
else
    log "WARNING: No auth_token found — run 'docker exec -it obsidian-palace ob login'"
fi

# 2. ~/.config/obsidian-headless/ → /data/obsidian-config/config/
#    This is where ob sync-setup writes vault sync configuration
#    (e.g. sync/<vault-id>/config.json). Without this, every container
#    restart requires a manual ob sync-setup — which was the root cause
#    of repeated vault wipe incidents.
mkdir -p "$PERSISTED_CONFIG/config" "/root/.config"
ln -sfn "$PERSISTED_CONFIG/config" "/root/.config/obsidian-headless"

SYNC_CONFIG="$PERSISTED_CONFIG/config/sync"
if [ -d "$SYNC_CONFIG" ] && [ "$(find "$SYNC_CONFIG" -name 'config.json' -type f 2>/dev/null | wc -l)" -gt 0 ]; then
    log "ob sync-setup config linked from $PERSISTED_CONFIG/config/"
else
    log "WARNING: No sync config found — run 'docker exec -it obsidian-palace ob sync-setup --vault <VAULT_ID> --path /data/vault'"
fi

# --- Migrate legacy config layout ---
# Previous versions stored auth_token directly in /data/obsidian-config/.
# Move it to the new headless/ subdirectory if found.
if [ -f "$PERSISTED_CONFIG/auth_token" ] && [ ! -f "$PERSISTED_CONFIG/headless/auth_token" ]; then
    log "Migrating legacy auth_token to new layout"
    mv "$PERSISTED_CONFIG/auth_token" "$PERSISTED_CONFIG/headless/auth_token"
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
