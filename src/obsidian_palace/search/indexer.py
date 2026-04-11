"""Vault indexer — index markdown files into MemPalace's ChromaDB.

Provides functions for initial full-vault indexing, single-file
re-indexing (on modification), and single-file removal (on deletion).

MemPalace is entirely synchronous — all heavy operations are wrapped
with ``asyncio.to_thread`` to avoid blocking the FastAPI event loop.
"""

import asyncio
import logging
from pathlib import Path

from obsidian_palace.config import get_settings

logger = logging.getLogger(__name__)

# Default room configuration for the Obsidian vault.
# Room routing in MemPalace works by matching folder names, filenames,
# and content keywords (first 2000 chars). Folder-name matching is
# priority 1, so these room names are chosen to align with typical
# vault top-level directories.
DEFAULT_ROOMS: list[dict] = [
    {
        "name": "daily_notes",
        "description": "Daily journal entries and logs",
        "keywords": ["daily", "journal", "log"],
    },
    {
        "name": "projects",
        "description": "Project notes, planning, and tasks",
        "keywords": ["project", "roadmap", "sprint", "task"],
    },
    {
        "name": "reference",
        "description": "Reference material, guides, and how-tos",
        "keywords": ["reference", "guide", "howto", "tutorial"],
    },
    {
        "name": "people",
        "description": "Notes about people and relationships",
        "keywords": ["people", "person", "contact"],
    },
    {
        "name": "technical",
        "description": "Technical notes, code, architecture",
        "keywords": ["code", "api", "architecture", "infrastructure", "terraform"],
    },
    {
        "name": "general",
        "description": "Everything that doesn't fit other rooms",
        "keywords": [],
    },
]


def _get_collection():
    """Get or create the ChromaDB collection for the vault.

    Returns:
        A ``chromadb.Collection`` instance.
    """
    from mempalace.palace import get_collection

    settings = get_settings()
    return get_collection(
        palace_path=str(settings.chromadb_path),
        collection_name=settings.mempalace_collection_name,
    )


def _index_file_sync(filepath: Path, vault_path: Path, wing: str) -> int:
    """Index a single markdown file into the palace. Synchronous.

    Uses MemPalace's ``process_file`` which chunks the content and
    upserts drawers into ChromaDB. Skips files that haven't changed
    since the last index (mtime check).

    Args:
        filepath: Absolute path to the markdown file.
        vault_path: Absolute path to the vault root.
        wing: MemPalace wing name.

    Returns:
        Number of drawers (chunks) indexed. 0 if skipped.
    """
    from mempalace.miner import process_file

    collection = _get_collection()
    drawer_count, room = process_file(
        filepath=filepath,
        project_path=vault_path,
        collection=collection,
        wing=wing,
        rooms=DEFAULT_ROOMS,
        agent="obsidian_palace",
        dry_run=False,
    )

    if drawer_count > 0:
        logger.debug("Indexed %s -> room=%s, drawers=%d", filepath.name, room, drawer_count)

    return drawer_count


def _remove_file_sync(source_file: str) -> int:
    """Remove all drawers for a source file from the palace. Synchronous.

    MemPalace does not provide a built-in delete-by-source function,
    so we query ChromaDB directly and delete matching drawer IDs.

    Args:
        source_file: The source_file value stored in drawer metadata
            (absolute path string as used during indexing).

    Returns:
        Number of drawers removed.
    """
    collection = _get_collection()

    try:
        results = collection.get(where={"source_file": source_file})
        ids = results.get("ids", [])
        if not ids:
            return 0
        collection.delete(ids=ids)
        logger.debug("Removed %d drawers for %s", len(ids), source_file)
        return len(ids)
    except Exception:
        logger.exception("Failed to remove drawers for %s", source_file)
        return 0


def _scan_vault_sync(vault_path: Path) -> list[Path]:
    """Scan the vault for all markdown files. Synchronous.

    Skips hidden directories (starting with '.') and non-markdown files.

    Args:
        vault_path: Absolute path to the vault root.

    Returns:
        List of absolute paths to markdown files.
    """
    md_files: list[Path] = []
    for path in vault_path.rglob("*.md"):
        # Skip hidden directories (.obsidian, .git, .trash, etc.)
        if any(part.startswith(".") for part in path.relative_to(vault_path).parts):
            continue
        md_files.append(path)
    return sorted(md_files)


def _index_vault_sync(vault_path: Path, wing: str) -> tuple[int, int]:
    """Index all markdown files in the vault. Synchronous.

    Scans the vault for .md files and indexes each one via MemPalace's
    ``process_file``. Files that haven't changed since the last index
    are automatically skipped (mtime check in process_file).

    Args:
        vault_path: Absolute path to the vault root.
        wing: MemPalace wing name.

    Returns:
        Tuple of (files_processed, total_drawers).
    """
    md_files = _scan_vault_sync(vault_path)
    logger.info("Found %d markdown files in vault", len(md_files))

    total_drawers = 0
    files_processed = 0

    for filepath in md_files:
        count = _index_file_sync(filepath, vault_path, wing)
        if count > 0:
            files_processed += 1
            total_drawers += count

    return files_processed, total_drawers


async def index_vault() -> tuple[int, int]:
    """Index the entire vault into MemPalace.

    Runs the synchronous full-vault scan and indexing in a thread
    to avoid blocking the event loop. Files already indexed with
    unchanged mtimes are skipped automatically.

    Returns:
        Tuple of (files_processed, total_drawers).
    """
    settings = get_settings()

    if not settings.mempalace_enabled:
        logger.info("MemPalace disabled — skipping vault indexing")
        return 0, 0

    vault_path = settings.vault_path.resolve()
    wing = settings.mempalace_wing

    logger.info("Starting vault indexing: vault=%s, wing=%s", vault_path, wing)

    files_processed, total_drawers = await asyncio.to_thread(
        _index_vault_sync,
        vault_path=vault_path,
        wing=wing,
    )

    logger.info(
        "Vault indexing complete: %d files processed, %d drawers created",
        files_processed,
        total_drawers,
    )
    return files_processed, total_drawers


async def index_file(filepath: Path) -> int:
    """Index or re-index a single file into MemPalace.

    Args:
        filepath: Absolute path to the markdown file.

    Returns:
        Number of drawers (chunks) indexed. 0 if skipped.
    """
    settings = get_settings()

    if not settings.mempalace_enabled:
        return 0

    vault_path = settings.vault_path.resolve()
    wing = settings.mempalace_wing

    return await asyncio.to_thread(
        _index_file_sync,
        filepath=filepath,
        vault_path=vault_path,
        wing=wing,
    )


async def remove_file(filepath: Path) -> int:
    """Remove a file's index entries from MemPalace.

    Args:
        filepath: Absolute path to the deleted markdown file.

    Returns:
        Number of drawers removed.
    """
    settings = get_settings()

    if not settings.mempalace_enabled:
        return 0

    return await asyncio.to_thread(_remove_file_sync, source_file=str(filepath))
