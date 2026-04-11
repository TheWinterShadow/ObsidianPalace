"""Tests for MemPalace search integration.

MemPalace/ChromaDB cannot import on Python 3.14 (Pydantic v1
incompatibility), so the ``_search_sync`` tests inject a fake
``mempalace.searcher`` module via ``sys.modules`` before calling
the function.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from obsidian_palace.search.searcher import SearchResult, search


@pytest.fixture()
def fake_mempalace():
    """Inject a fake mempalace.searcher module to avoid ChromaDB import crash."""
    fake_mod = ModuleType("mempalace.searcher")
    fake_mod.search_memories = MagicMock()  # type: ignore[attr-defined]

    # Also need a fake mempalace parent module
    fake_parent = ModuleType("mempalace")
    originals = {
        "mempalace": sys.modules.get("mempalace"),
        "mempalace.searcher": sys.modules.get("mempalace.searcher"),
    }
    sys.modules["mempalace"] = fake_parent
    sys.modules["mempalace.searcher"] = fake_mod

    yield fake_mod.search_memories

    # Restore originals
    for key, val in originals.items():
        if val is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = val


class TestSearchSync:
    """Tests for the synchronous search wrapper via _search_sync."""

    def test_returns_mapped_results(self, fake_mempalace: MagicMock) -> None:
        from obsidian_palace.search.searcher import _search_sync

        fake_mempalace.return_value = {
            "query": "test",
            "filters": {"wing": "obsidian", "room": None},
            "results": [
                {
                    "text": "Some note content about testing.",
                    "wing": "obsidian",
                    "room": "projects",
                    "source_file": "Projects/test.md",
                    "similarity": 0.85,
                },
                {
                    "text": "Another result about tests.",
                    "wing": "obsidian",
                    "room": "general",
                    "source_file": "Inbox/notes.md",
                    "similarity": 0.72,
                },
            ],
        }

        results = _search_sync("test", palace_path="/data/chromadb", wing="obsidian", n_results=5)

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].content == "Some note content about testing."
        assert results[0].source_path == "Projects/test.md"
        assert results[0].score == 0.85
        assert results[0].metadata == {"wing": "obsidian", "room": "projects"}

        assert results[1].score == 0.72

        fake_mempalace.assert_called_once_with(
            query="test",
            palace_path="/data/chromadb",
            wing="obsidian",
            n_results=5,
        )

    def test_returns_empty_on_error(self, fake_mempalace: MagicMock) -> None:
        from obsidian_palace.search.searcher import _search_sync

        fake_mempalace.return_value = {
            "error": "No palace found",
            "hint": "Run: mempalace init",
        }

        results = _search_sync("test", palace_path="/data/chromadb")

        assert results == []

    def test_returns_empty_on_no_results(self, fake_mempalace: MagicMock) -> None:
        from obsidian_palace.search.searcher import _search_sync

        fake_mempalace.return_value = {
            "query": "obscure topic",
            "filters": {"wing": None, "room": None},
            "results": [],
        }

        results = _search_sync("obscure topic", palace_path="/data/chromadb")

        assert results == []


class TestSearchAsync:
    """Tests for the async search function."""

    @patch("obsidian_palace.search.searcher._search_sync")
    async def test_delegates_to_sync(self, mock_sync: MagicMock, test_settings) -> None:
        mock_sync.return_value = [
            SearchResult(
                content="Found it",
                source_path="test.md",
                score=0.9,
                metadata={"wing": "obsidian", "room": "general"},
            )
        ]

        results = await search("find me", limit=5)

        assert len(results) == 1
        assert results[0].content == "Found it"
        mock_sync.assert_called_once_with(
            query="find me",
            palace_path=str(test_settings.chromadb_path),
            wing="obsidian",
            n_results=5,
        )

    async def test_returns_empty_when_disabled(self, test_settings) -> None:
        test_settings.mempalace_enabled = False

        with patch("obsidian_palace.search.searcher.get_settings", return_value=test_settings):
            results = await search("anything")

        assert results == []
