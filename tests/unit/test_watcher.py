"""Tests for the vault file watcher."""

from pathlib import Path

from obsidian_palace.search.watcher import _should_index


class TestShouldIndex:
    """Tests for the file change filter."""

    def test_accepts_markdown_files(self, tmp_vault: Path) -> None:
        assert _should_index(str(tmp_vault / "Projects" / "note.md"), tmp_vault) is True

    def test_rejects_non_markdown(self, tmp_vault: Path) -> None:
        assert _should_index(str(tmp_vault / "image.png"), tmp_vault) is False
        assert _should_index(str(tmp_vault / "data.json"), tmp_vault) is False

    def test_rejects_hidden_directories(self, tmp_vault: Path) -> None:
        assert _should_index(str(tmp_vault / ".obsidian" / "config.md"), tmp_vault) is False
        assert _should_index(str(tmp_vault / ".git" / "HEAD.md"), tmp_vault) is False
        assert _should_index(str(tmp_vault / ".trash" / "old.md"), tmp_vault) is False

    def test_rejects_path_outside_vault(self, tmp_vault: Path) -> None:
        assert _should_index("/some/other/path/note.md", tmp_vault) is False

    def test_accepts_nested_markdown(self, tmp_vault: Path) -> None:
        deep = tmp_vault / "Projects" / "Sub" / "Deep" / "note.md"
        assert _should_index(str(deep), tmp_vault) is True
