"""File watcher for re-indexing vault changes into MemPalace.

Uses watchfiles to monitor the vault directory for changes and
triggers re-indexing of modified files into the ChromaDB index.
"""

import asyncio
import logging

from obsidian_palace.config import get_settings

logger = logging.getLogger(__name__)


async def watch_vault() -> None:
    """Watch the vault directory for file changes and re-index.

    Runs as a background task during the application lifecycle.
    Monitors for .md file creates, modifications, and deletions.
    """
    settings = get_settings()
    vault_path = settings.vault_path

    logger.info("Starting vault file watcher: %s", vault_path)

    # TODO: Phase 3 — implement with watchfiles
    # from watchfiles import awatch, Change
    #
    # async for changes in awatch(vault_path):
    #     for change_type, path in changes:
    #         if not path.endswith(".md"):
    #             continue
    #         relative = Path(path).relative_to(vault_path)
    #         if change_type in (Change.added, Change.modified):
    #             logger.info("Re-indexing: %s", relative)
    #             # await index_file(path)
    #         elif change_type == Change.deleted:
    #             logger.info("Removing from index: %s", relative)
    #             # await remove_from_index(path)

    # Placeholder — keep the coroutine alive
    while True:
        await asyncio.sleep(3600)
