"""Tests for vault file operations."""

from pathlib import Path

import pytest

from obsidian_palace.vault.operations import (
    list_folders,
    list_notes,
    read_note,
    write_note,
)


class TestReadNote:
    async def test_read_existing_note(self, tmp_vault: Path) -> None:
        content = await read_note("Projects/ObsidianPalace/design.md")
        assert "MCP server for Obsidian vault access" in content

    async def test_read_nonexistent_note(self) -> None:
        with pytest.raises(FileNotFoundError):
            await read_note("nonexistent/note.md")

    async def test_read_path_traversal_blocked(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            await read_note("../../etc/passwd")


class TestWriteNote:
    async def test_write_new_note(self, tmp_vault: Path) -> None:
        path = await write_note("00_Inbox/test-note.md", "# Test\n\nContent here.\n")
        assert path.exists()
        assert path.read_text() == "# Test\n\nContent here.\n"

    async def test_write_creates_parent_dirs(self, tmp_vault: Path) -> None:
        path = await write_note("New/Nested/Dir/note.md", "# Nested\n")
        assert path.exists()
        assert (tmp_vault / "New" / "Nested" / "Dir").is_dir()

    async def test_write_path_traversal_blocked(self) -> None:
        with pytest.raises(ValueError, match="Path traversal"):
            await write_note("../../../tmp/evil.md", "bad stuff")


class TestListFolders:
    async def test_list_root_folders(self) -> None:
        folders = await list_folders()
        assert "Projects" in folders
        assert "00_Inbox" in folders
        assert "Daily Notes" in folders
        assert "References" in folders

    async def test_list_subfolder(self) -> None:
        folders = await list_folders("Projects")
        assert "ObsidianPalace" in folders

    async def test_list_nonexistent_folder(self) -> None:
        with pytest.raises(FileNotFoundError):
            await list_folders("nonexistent")


class TestListNotes:
    async def test_list_notes_in_folder(self) -> None:
        notes = await list_notes("00_Inbox")
        assert "quick-note.md" in notes

    async def test_list_notes_nonexistent_returns_empty(self) -> None:
        notes = await list_notes("nonexistent")
        assert notes == []
