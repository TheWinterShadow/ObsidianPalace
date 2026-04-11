"""Tests for the vault indexer module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from obsidian_palace.search.indexer import (
    _remove_file_sync,
    _scan_vault_sync,
    index_file,
    index_vault,
    remove_file,
)


class TestScanVaultSync:
    """Tests for vault scanning — no MemPalace dependency."""

    def test_finds_markdown_files(self, tmp_vault: Path) -> None:
        files = _scan_vault_sync(tmp_vault)

        names = [f.name for f in files]
        assert "design.md" in names
        assert "2025-04-11.md" in names
        assert "quick-note.md" in names

    def test_skips_hidden_directories(self, tmp_vault: Path) -> None:
        hidden_dir = tmp_vault / ".obsidian"
        hidden_dir.mkdir()
        (hidden_dir / "config.md").write_text("# Hidden\n")

        files = _scan_vault_sync(tmp_vault)

        paths_str = [str(f) for f in files]
        assert not any(".obsidian" in p for p in paths_str)

    def test_returns_sorted(self, tmp_vault: Path) -> None:
        files = _scan_vault_sync(tmp_vault)

        assert files == sorted(files)

    def test_empty_vault(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty_vault"
        empty.mkdir()

        files = _scan_vault_sync(empty)

        assert files == []


class TestRemoveFileSync:
    """Tests for removing a file's drawers from the index."""

    @patch("obsidian_palace.search.indexer._get_collection")
    def test_removes_matching_drawers(self, mock_coll: MagicMock) -> None:
        collection = MagicMock()
        collection.get.return_value = {"ids": ["drawer_1", "drawer_2"]}
        mock_coll.return_value = collection

        count = _remove_file_sync("/data/vault/Projects/test.md")

        assert count == 2
        collection.delete.assert_called_once_with(ids=["drawer_1", "drawer_2"])

    @patch("obsidian_palace.search.indexer._get_collection")
    def test_returns_zero_when_not_found(self, mock_coll: MagicMock) -> None:
        collection = MagicMock()
        collection.get.return_value = {"ids": []}
        mock_coll.return_value = collection

        count = _remove_file_sync("/data/vault/gone.md")

        assert count == 0
        collection.delete.assert_not_called()

    @patch("obsidian_palace.search.indexer._get_collection")
    def test_returns_zero_on_exception(self, mock_coll: MagicMock) -> None:
        collection = MagicMock()
        collection.get.side_effect = RuntimeError("ChromaDB error")
        mock_coll.return_value = collection

        count = _remove_file_sync("/data/vault/broken.md")

        assert count == 0


class TestIndexFile:
    """Tests for single-file async indexing."""

    @patch("obsidian_palace.search.indexer._index_file_sync")
    async def test_delegates_to_sync(self, mock_sync: MagicMock) -> None:
        mock_sync.return_value = 5

        count = await index_file(Path("/data/vault/test.md"))

        assert count == 5
        mock_sync.assert_called_once()

    async def test_returns_zero_when_disabled(self, test_settings) -> None:
        test_settings.mempalace_enabled = False

        with patch("obsidian_palace.search.indexer.get_settings", return_value=test_settings):
            count = await index_file(Path("/data/vault/test.md"))

        assert count == 0


class TestRemoveFile:
    """Tests for single-file async removal."""

    @patch("obsidian_palace.search.indexer._remove_file_sync")
    async def test_delegates_to_sync(self, mock_sync: MagicMock) -> None:
        mock_sync.return_value = 3

        count = await remove_file(Path("/data/vault/deleted.md"))

        assert count == 3

    async def test_returns_zero_when_disabled(self, test_settings) -> None:
        test_settings.mempalace_enabled = False

        with patch("obsidian_palace.search.indexer.get_settings", return_value=test_settings):
            count = await remove_file(Path("/data/vault/deleted.md"))

        assert count == 0


class TestIndexVault:
    """Tests for full vault async indexing."""

    @patch("obsidian_palace.search.indexer._index_vault_sync")
    async def test_delegates_to_sync(self, mock_sync: MagicMock) -> None:
        mock_sync.return_value = (10, 50)

        files, drawers = await index_vault()

        assert files == 10
        assert drawers == 50

    async def test_returns_zero_when_disabled(self, test_settings) -> None:
        test_settings.mempalace_enabled = False

        with patch("obsidian_palace.search.indexer.get_settings", return_value=test_settings):
            files, drawers = await index_vault()

        assert files == 0
        assert drawers == 0
