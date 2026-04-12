#!/bin/bash
# sync-guard.sh — Safety wrapper around ob sync.
#
# Runs THREE checks before starting ob sync --continuous:
#
# 1. Credential gate: Verifies ob login auth_token exists.
#    Without this, ob sync will fail immediately.
#
# 2. Sync config gate: Verifies ob sync-setup has been run by checking
#    for config.json in ~/.config/obsidian-headless/sync/<vault-id>/.
#    Without this, ob sync connects in a broken state.
#
# 3. File count gate: Counts .md files in the vault. If the count is below
#    a safety threshold, refuses to sync. This prevents a scenario where a
#    misconfigured or corrupted vault peer tells Obsidian Sync "I have no
#    files," causing deletions to propagate to all connected devices.
#
# If any check fails, this script exits non-zero. Supervisord will retry
# up to startretries times, then mark the process as FATAL. The MCP server
# continues running and serves whatever is on disk.

set -euo pipefail

VAULT_PATH="/data/vault"
PERSISTED_CONFIG="/data/obsidian-config"
MIN_VAULT_FILES="${OBSIDIAN_PALACE_MIN_VAULT_FILES:-10}"

log() { echo "[sync-guard] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

# --- Gate 1: Credential check ---
AUTH_TOKEN="$PERSISTED_CONFIG/headless/auth_token"
if [ ! -f "$AUTH_TOKEN" ]; then
    # Also check legacy path
    if [ ! -f "$PERSISTED_CONFIG/auth_token" ]; then
        log "BLOCKED: No auth_token found"
        log "Run 'docker exec -it obsidian-palace ob login' to authenticate"
        exit 1
    fi
fi

# --- Gate 2: Sync config check ---
# ob sync-setup writes config to ~/.config/obsidian-headless/sync/<vault-id>/config.json.
# The entrypoint symlinks this to /data/obsidian-config/config/.
SYNC_CONFIG_DIR="$PERSISTED_CONFIG/config/sync"
SYNC_CONFIG_COUNT=$(find "$SYNC_CONFIG_DIR" -name 'config.json' -type f 2>/dev/null | wc -l)
if [ "$SYNC_CONFIG_COUNT" -eq 0 ]; then
    log "BLOCKED: No sync config found in $SYNC_CONFIG_DIR"
    log "Run 'docker exec -it obsidian-palace ob sync-setup --vault <VAULT_ID> --path $VAULT_PATH'"
    exit 1
fi
log "Found $SYNC_CONFIG_COUNT vault sync config(s)"

# --- Gate 3: Vault file count safety check ---
MD_COUNT=$(find "$VAULT_PATH" -name '*.md' -type f 2>/dev/null | wc -l)
log "Vault contains $MD_COUNT .md files (minimum required: $MIN_VAULT_FILES)"

if [ "$MD_COUNT" -lt "$MIN_VAULT_FILES" ]; then
    log "BLOCKED: Vault has fewer than $MIN_VAULT_FILES .md files"
    log "This safety check prevents an empty or corrupted vault from propagating"
    log "deletions to all Obsidian Sync devices."
    log ""
    log "If this is a genuinely new/small vault, set OBSIDIAN_PALACE_MIN_VAULT_FILES"
    log "to a lower value. Current threshold: $MIN_VAULT_FILES"
    exit 1
fi

# --- All gates passed — start sync ---
log "All safety checks passed. Starting ob sync --continuous"
exec ob sync --continuous --path "$VAULT_PATH"
