#!/bin/bash
# sync-guard.sh — Safety wrapper around ob sync.
#
# Runs TWO checks before starting ob sync --continuous:
#
# 1. Credential gate: Verifies ob login credentials and sync config exist.
#    Without these, ob sync will either fail or connect in a broken state.
#
# 2. File count gate: Counts .md files in the vault. If the count is below
#    a safety threshold, refuses to sync. This prevents a scenario where a
#    misconfigured or corrupted vault peer tells Obsidian Sync "I have no
#    files," causing deletions to propagate to all connected devices.
#
# If either check fails, this script exits non-zero. Supervisord will retry
# up to startretries times, then mark the process as FATAL. The MCP server
# continues running and serves whatever is on disk.

set -euo pipefail

VAULT_PATH="/data/vault"
PERSISTED_CONFIG="/data/obsidian-config"
MIN_VAULT_FILES="${OBSIDIAN_PALACE_MIN_VAULT_FILES:-10}"

log() { echo "[sync-guard] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"; }

# --- Gate 1: Credential check ---
if [ ! -f "$PERSISTED_CONFIG/auth_token" ]; then
    log "BLOCKED: No auth_token found at $PERSISTED_CONFIG/auth_token"
    log "Run 'docker exec -it obsidian-palace ob login' to authenticate"
    exit 1
fi

# --- Gate 2: Sync config check ---
# ob sync-setup writes config to /data/vault/.obsidian/sync-*
SYNC_CONFIG_COUNT=$(find "$VAULT_PATH/.obsidian" -name 'sync-*' -type f 2>/dev/null | wc -l)
if [ "$SYNC_CONFIG_COUNT" -eq 0 ]; then
    log "BLOCKED: No sync config found in $VAULT_PATH/.obsidian/"
    log "Run 'docker exec -it obsidian-palace ob sync-setup --vault <VAULT_ID> --path $VAULT_PATH'"
    exit 1
fi

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
