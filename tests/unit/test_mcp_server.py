"""Tests for MCP server tool dispatch."""

from pathlib import Path
from unittest.mock import patch

from obsidian_palace.mcp.server import handle_call_tool, handle_list_tools
from obsidian_palace.search.searcher import SearchResult


class TestListTools:
    async def test_returns_all_tools(self) -> None:
        tools = await handle_list_tools()
        names = {t.name for t in tools}
        assert names == {"search_vault", "read_note", "write_note", "list_folders", "list_notes"}

    async def test_tools_have_input_schemas(self) -> None:
        tools = await handle_list_tools()
        for tool in tools:
            assert "type" in tool.inputSchema
            assert tool.inputSchema["type"] == "object"


class TestCallTool:
    async def test_unknown_tool(self) -> None:
        result = await handle_call_tool("nonexistent", {})
        assert len(result) == 1
        assert "Unknown tool" in result[0].text

    async def test_read_note(self, tmp_vault: Path) -> None:
        result = await handle_call_tool("read_note", {"path": "Projects/ObsidianPalace/design.md"})
        assert len(result) == 1
        assert "MCP server for Obsidian vault access" in result[0].text

    async def test_read_note_not_found(self) -> None:
        result = await handle_call_tool("read_note", {"path": "nonexistent.md"})
        assert len(result) == 1
        assert "Error:" in result[0].text

    async def test_write_note(self, tmp_vault: Path) -> None:
        result = await handle_call_tool(
            "write_note",
            {"content": "# Test\n\nTest content.", "path": "Inbox/mcp-test.md"},
        )
        assert len(result) == 1
        assert "Note written to" in result[0].text
        assert (tmp_vault / "Inbox" / "mcp-test.md").exists()

    async def test_write_note_ai_placement_fallback(self, tmp_vault: Path) -> None:
        """Without an API key, AI placement falls back to Inbox/."""
        result = await handle_call_tool(
            "write_note",
            {"content": "# No path given\n\nShould go to Inbox.", "title": "fallback-test"},
        )
        assert len(result) == 1
        assert "Inbox/fallback-test.md" in result[0].text

    async def test_list_folders(self) -> None:
        result = await handle_call_tool("list_folders", {"path": ""})
        assert len(result) == 1
        assert "Projects/" in result[0].text
        assert "Inbox/" in result[0].text

    async def test_list_notes(self) -> None:
        result = await handle_call_tool("list_notes", {"path": "Inbox"})
        assert len(result) == 1
        assert "quick-note.md" in result[0].text

    async def test_search_vault_empty(self) -> None:
        """Search returns empty when no results match."""
        with patch("obsidian_palace.mcp.server.search", return_value=[]):
            result = await handle_call_tool("search_vault", {"query": "test query"})
        assert len(result) == 1
        assert "No results" in result[0].text

    async def test_search_vault_with_results(self) -> None:
        """Search returns formatted results when matches are found."""
        mock_results = [
            SearchResult(
                content="This is a note about Python testing best practices.",
                source_path="Projects/python-testing.md",
                score=0.92,
                metadata={"wing": "obsidian", "room": "projects"},
            ),
            SearchResult(
                content="Unit tests should be fast and isolated.",
                source_path="Reference/testing-guide.md",
                score=0.78,
                metadata={"wing": "obsidian", "room": "reference"},
            ),
        ]

        with patch("obsidian_palace.mcp.server.search", return_value=mock_results):
            result = await handle_call_tool("search_vault", {"query": "testing"})

        assert len(result) == 1
        assert "Found 2 results" in result[0].text
        assert "python-testing.md" in result[0].text
        assert "0.920" in result[0].text
        assert "testing-guide.md" in result[0].text

    async def test_call_tool_with_none_arguments(self) -> None:
        result = await handle_call_tool("list_folders", None)
        assert len(result) == 1
        assert "Folders" in result[0].text
