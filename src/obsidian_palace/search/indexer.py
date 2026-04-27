"""Vault indexer — index markdown files into MemPalace's ChromaDB.

Provides functions for initial full-vault indexing, single-file
re-indexing (on modification), and single-file removal (on deletion).

MemPalace is entirely synchronous — all heavy operations are wrapped
with ``asyncio.to_thread`` to avoid blocking the FastAPI event loop.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from obsidian_palace.config import get_settings

logger = logging.getLogger(__name__)

# Number of concurrent worker threads for vault indexing.
# The ChromaDB collection object is initialized once and shared;
# collection.upsert() is safe for concurrent use.
_INDEX_WORKERS = 4

# Default room configuration for the Obsidian vault.
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


def _get_collection() -> Any:
    """Get or create the ChromaDB collection for the vault.

    Must be called from a single thread before passing the returned
    collection to concurrent workers. ChromaDB's PersistentClient
    is not safe to initialize from multiple threads simultaneously.

    Returns:
        A ``chromadb.Collection`` instance.
    """
    from mempalace.palace import get_collection

    settings = get_settings()
    return get_collection(
        palace_path=str(settings.chromadb_path),
        collection_name=settings.mempalace_collection_name,
    )


def _index_file_sync(filepath: Path, vault_path: Path, wing: str, collection: Any) -> int:
    """Index a single markdown file into the palace. Synchronous.

    Uses MemPalace's ``process_file`` which chunks the content and
    upserts drawers into ChromaDB. Skips files that haven't changed
    since the last index (mtime check).

    Args:
        filepath: Absolute path to the markdown file.
        vault_path: Absolute path to the vault root.
        wing: MemPalace wing name.
        collection: Shared ChromaDB collection instance. Must be
            initialized on the calling thread before passing here.

    Returns:
        Number of drawers (chunks) indexed. 0 if skipped.
    """
    from mempalace.miner import process_file

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

    Args:
        source_file: The source_file value stored in drawer metadata.

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

    Args:
        vault_path: Absolute path to the vault root.

    Returns:
        List of absolute paths to markdown files.
    """
    md_files: list[Path] = []
    for path in vault_path.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(vault_path).parts):
            continue
        md_files.append(path)
    return sorted(md_files)


def _index_vault_sync(vault_path: Path, wing: str) -> tuple[int, int]:
    """Index all markdown files in the vault concurrently. Synchronous.

    Initializes the ChromaDB collection once on the calling thread,
    then fans out to a thread pool for concurrent ONNX inference.
    ChromaDB PersistentClient is not thread-safe to initialize
    concurrently — this pattern avoids that race entirely.

    Args:
        vault_path: Absolute path to the vault root.
        wing: MemPalace wing name.

    Returns:
        Tuple of (files_processed, total_drawers).
    """
    md_files = _scan_vault_sync(vault_path)
    total_files = len(md_files)
    logger.info("Found %d markdown files in vault", total_files)

    # Initialize collection once here — not inside worker threads.
    # ChromaDB PersistentClient init is not thread-safe.
    collection = _get_collection()

    total_drawers = 0
    files_processed = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=_INDEX_WORKERS) as executor:
        futures = {
            executor.submit(_index_file_sync, fp, vault_path, wing, collection): fp
            for fp in md_files
        }
        for future in as_completed(futures):
            completed += 1
            filepath = futures[future]
            try:
                count = future.result()
                if count > 0:
                    files_processed += 1
                    total_drawers += count
            except Exception:
                logger.exception("Failed to index %s", filepath.name)

            if completed % 100 == 0 or completed == total_files:
                logger.info(
                    "Indexing progress: %d/%d files complete, %d drawers so far",
                    completed,
                    total_files,
                    total_drawers,
                )

    return files_processed, total_drawers


async def index_vault() -> tuple[int, int]:
    """Index the entire vault into MemPalace."""
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
    """Index or re-index a single file into MemPalace."""
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
        collection=_get_collection(),
    )


async def remove_file(filepath: Path) -> int:
    """Remove a file's index entries from MemPalace."""
    settings = get_settings()

    if not settings.mempalace_enabled:
        return 0

    return await asyncio.to_thread(_remove_file_sync, source_file=str(filepath))
