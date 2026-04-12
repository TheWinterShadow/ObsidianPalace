"""Vault file operations — read, write, list, and path utilities.

All file operations are scoped to the configured vault directory.
Path traversal is prevented by validating resolved paths stay within
the vault root.
"""

import logging
from datetime import date
from pathlib import Path

from obsidian_palace.config import get_settings

logger = logging.getLogger(__name__)


def _resolve_vault_path(relative_path: str) -> Path:
    """Resolve a relative path to an absolute path within the vault.

    Args:
        relative_path: Path relative to the vault root.

    Returns:
        The resolved absolute path.

    Raises:
        ValueError: If the resolved path escapes the vault directory.
    """
    settings = get_settings()
    vault_root = settings.vault_path.resolve()
    target = (vault_root / relative_path).resolve()

    if not str(target).startswith(str(vault_root)):
        raise ValueError(f"Path traversal detected: {relative_path}")

    return target


async def read_note(relative_path: str) -> str:
    """Read a note's content from the vault.

    Args:
        relative_path: Path to the note relative to vault root.

    Returns:
        The note content as a string.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the path escapes the vault.
    """
    target = _resolve_vault_path(relative_path)
    if not target.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    return target.read_text(encoding="utf-8")


async def write_note(relative_path: str, content: str) -> Path:
    """Write content to a note in the vault.

    Creates parent directories as needed. Obsidian Sync will
    pick up the change on the next sync cycle.

    Args:
        relative_path: Path to the note relative to vault root.
        content: Markdown content to write.

    Returns:
        The absolute path of the written file.

    Raises:
        ValueError: If the path escapes the vault.
    """
    target = _resolve_vault_path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info("Wrote note: %s (%d bytes)", relative_path, len(content))
    return target


async def list_folders(relative_path: str = "") -> list[str]:
    """List subdirectories under a vault path.

    Args:
        relative_path: Subfolder to list (default: vault root).

    Returns:
        Sorted list of subfolder names.

    Raises:
        ValueError: If the path escapes the vault.
        FileNotFoundError: If the path does not exist.
    """
    target = _resolve_vault_path(relative_path)
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {relative_path}")

    return sorted(
        entry.name
        for entry in target.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


async def list_notes(relative_path: str = "", extensions: tuple[str, ...] = (".md",)) -> list[str]:
    """List note files under a vault path.

    Args:
        relative_path: Subfolder to list (default: vault root).
        extensions: File extensions to include.

    Returns:
        Sorted list of note filenames.

    Raises:
        ValueError: If the path escapes the vault.
    """
    target = _resolve_vault_path(relative_path)
    if not target.exists():
        return []

    return sorted(
        entry.name for entry in target.iterdir() if entry.is_file() and entry.suffix in extensions
    )


async def notes_for_date(target_date: date, extensions: tuple[str, ...] = (".md",)) -> list[str]:
    """Find all notes in the vault last modified on a given date.

    Walks the entire vault recursively and returns vault-relative paths
    for every note whose mtime matches ``target_date``.

    Args:
        target_date: The calendar date to filter by.
        extensions: File extensions to include.

    Returns:
        Sorted list of vault-relative paths (e.g. ``"Daily Notes/2025-04-11.md"``).
    """
    settings = get_settings()
    vault_root = settings.vault_path.resolve()

    results: list[str] = []
    for p in vault_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in extensions:
            continue
        # Skip hidden directories anywhere in the path
        if any(part.startswith(".") for part in p.parts):
            continue
        mtime_date = date.fromtimestamp(p.stat().st_mtime)
        if mtime_date == target_date:
            results.append(str(p.relative_to(vault_root)))

    return sorted(results)
