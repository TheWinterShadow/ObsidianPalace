"""File watcher for re-indexing vault changes into MemPalace.

Uses ``watchfiles`` to monitor the vault directory for markdown file
changes and triggers incremental re-indexing into the ChromaDB index.
Handles file creation, modification, and deletion events.
"""

import logging
from pathlib import Path

from watchfiles import Change, awatch

from obsidian_palace.config import get_settings
from obsidian_palace.search.indexer import index_file, remove_file

logger = logging.getLogger(__name__)


def _should_index(path: str, vault_path: Path) -> bool:
    """Check whether a changed file should be indexed.

    Filters to markdown files and excludes hidden directories
    (.obsidian, .git, .trash, etc.). Also used as the ``watch_filter``
    for ``awatch`` so that watchfiles itself skips irrelevant events
    (preventing "N changes detected" log spam from ob sync writes).

    Args:
        path: Absolute path string from the watch event.
        vault_path: Resolved vault root path.

    Returns:
        True if the file should be indexed/removed.
    """
    if not path.endswith(".md"):
        return False

    try:
        relative = Path(path).relative_to(vault_path)
    except ValueError:
        return False

    # Skip hidden directories
    return not any(part.startswith(".") for part in relative.parts)


def _make_watch_filter(vault_path: Path):
    """Create a watch filter function for ``awatch``.

    Returns a callable that ``watchfiles`` invokes for every raw
    filesystem event *before* logging or yielding it. Returning
    ``False`` suppresses the event entirely, which eliminates the
    "N changes detected" log noise from non-markdown writes
    (e.g. ob sync updating ``.obsidian/`` state files).
    """

    def watch_filter(change: Change, path: str) -> bool:  # noqa: ARG001
        return _should_index(path, vault_path)

    return watch_filter


async def watch_vault() -> None:
    """Watch the vault directory for file changes and re-index.

    Runs as a background task during the application lifecycle.
    Monitors for ``.md`` file creates, modifications, and deletions.
    Uses ``watchfiles.awatch`` for efficient async filesystem monitoring.

    On create/modify: re-indexes the file via MemPalace (mtime-aware,
    so unchanged files are skipped).
    On delete: removes the file's drawers from the ChromaDB index.
    """
    settings = get_settings()

    if not settings.mempalace_enabled:
        logger.info("MemPalace disabled — file watcher not started")
        return

    vault_path = settings.vault_path.resolve()
    logger.info("Starting vault file watcher: %s", vault_path)

    watch_filter = _make_watch_filter(vault_path)
    async for changes in awatch(vault_path, watch_filter=watch_filter):
        for change_type, path in changes:
            relative = Path(path).relative_to(vault_path)

            if change_type in (Change.added, Change.modified):
                logger.info("Re-indexing: %s (%s)", relative, change_type.name)
                try:
                    count = await index_file(Path(path))
                    if count > 0:
                        logger.info("Indexed %d drawers for %s", count, relative)
                except Exception:
                    logger.exception("Failed to re-index %s", relative)

            elif change_type == Change.deleted:
                logger.info("Removing from index: %s", relative)
                try:
                    count = await remove_file(Path(path))
                    if count > 0:
                        logger.info("Removed %d drawers for %s", count, relative)
                except Exception:
                    logger.exception("Failed to remove index for %s", relative)
