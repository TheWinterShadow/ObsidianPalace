"""Shared test fixtures for ObsidianPalace."""

from pathlib import Path
from unittest.mock import patch

import pytest

from obsidian_palace.config import Settings


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Create a temporary vault directory with sample structure."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Create sample folders
    (vault / "Projects").mkdir()
    (vault / "Projects" / "ObsidianPalace").mkdir()
    (vault / "Daily Notes").mkdir()
    (vault / "Inbox").mkdir()
    (vault / "References").mkdir()

    # Create sample notes
    (vault / "Projects" / "ObsidianPalace" / "design.md").write_text(
        "# ObsidianPalace Design\n\nMCP server for Obsidian vault access.\n"
    )
    (vault / "Daily Notes" / "2025-04-11.md").write_text(
        "# 2025-04-11\n\nStarted scaffolding ObsidianPalace.\n"
    )
    (vault / "Inbox" / "quick-note.md").write_text("# Quick Note\n\nSome quick thoughts.\n")

    return vault


@pytest.fixture
def test_settings(tmp_vault: Path, tmp_path: Path) -> Settings:
    """Create test settings pointing at the temporary vault."""
    return Settings(
        vault_path=tmp_vault,
        chromadb_path=tmp_path / "chromadb",
        allowed_email="test@example.com",
        google_client_id="test-client-id",
        google_client_secret="test-secret",
        mempalace_enabled=True,
        mempalace_wing="obsidian",
        mempalace_collection_name="mempalace_drawers",
    )


@pytest.fixture(autouse=True)
def _override_settings(test_settings: Settings) -> None:
    """Override get_settings globally in tests to use temp dirs."""
    with patch("obsidian_palace.config._settings", test_settings):
        yield
