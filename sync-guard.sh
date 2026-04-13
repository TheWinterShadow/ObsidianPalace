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
# 3. File count gate: Counts .md files in the vault and compares against
#    a percentage of the last known good count (stored on persistent disk).
#    This prevents a scenario where a misconfigured or corrupted vault peer
#    tells Obsidian Sync "I have no files," causing deletions to propagate
#    to all connected devices. On first boot (no state file), falls back to
#    an absolute minimum floor.
#
# If any check fails, this script exits non-zero. Supervisord will retry
# up to startretries times, then mark the process as FATAL. The MCP server
# continues running and serves whatever is on disk.

set -euo pipefail

VAULT_PATH="/data/vault"
PERSISTED_CONFIG="/data/obsidian-config"
STATE_FILE="/data/state/last_vault_count"
MIN_VAULT_PERCENT="${OBSIDIAN_PALACE_MIN_VAULT_PERCENT:-80}"
MIN_VAULT_FLOOR=1500

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

# --- Gate 3: Vault file count safety check (percentage-based) ---
MD_COUNT=$(find "$VAULT_PATH" -name '*.md' -type f 2>/dev/null | wc -l)

if [ -f "$STATE_FILE" ]; then
    LAST_GOOD_COUNT=$(cat "$STATE_FILE" 2>/dev/null || echo "0")
    # Validate that state file contains a number
    if ! [[ "$LAST_GOOD_COUNT" =~ ^[0-9]+$ ]]; then
        log "WARNING: State file contains invalid data ('$LAST_GOOD_COUNT'), treating as first boot"
        LAST_GOOD_COUNT=0
    fi
else
    LAST_GOOD_COUNT=0
fi

if [ "$LAST_GOOD_COUNT" -gt 0 ]; then
    # Normal path: compare against percentage of last known good count
    MIN_REQUIRED=$(( LAST_GOOD_COUNT * MIN_VAULT_PERCENT / 100 ))
    log "Vault contains $MD_COUNT .md files (last known good: $LAST_GOOD_COUNT, threshold: ${MIN_VAULT_PERCENT}% = $MIN_REQUIRED)"

    if [ "$MD_COUNT" -lt "$MIN_REQUIRED" ]; then
        log "BLOCKED: Vault has $MD_COUNT files, expected at least $MIN_REQUIRED (${MIN_VAULT_PERCENT}% of $LAST_GOOD_COUNT)"
        log "This safety check prevents an empty or corrupted vault from propagating"
        log "deletions to all Obsidian Sync devices."
        log ""
        log "If this drop is expected (e.g. large reorganization), delete the state file:"
        log "  rm $STATE_FILE"
        log "Or lower the threshold: set OBSIDIAN_PALACE_MIN_VAULT_PERCENT (current: $MIN_VAULT_PERCENT)"
        exit 1
    fi
else
    # First boot or missing state: use absolute floor as bootstrap
    log "Vault contains $MD_COUNT .md files (first boot — minimum floor: $MIN_VAULT_FLOOR)"

    if [ "$MD_COUNT" -lt "$MIN_VAULT_FLOOR" ]; then
        log "BLOCKED: Vault has $MD_COUNT files, expected at least $MIN_VAULT_FLOOR (first-boot floor)"
        log "This safety check prevents an empty vault from starting sync."
        log "If this is a genuinely small vault, wait for initial sync to populate files."
        exit 1
    fi
fi

# Gate 3 passed — record current count as last known good
echo "$MD_COUNT" > "$STATE_FILE"
log "Updated last known good count: $MD_COUNT"

# --- All gates passed — start sync ---
log "All safety checks passed. Starting ob sync --continuous"
exec ob sync --continuous --path "$VAULT_PATH"
