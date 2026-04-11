"""Tests for MCP server tool dispatch."""

from pathlib import Path

from obsidian_palace.mcp.server import handle_call_tool, handle_list_tools


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
        """Search returns empty until MemPalace is integrated."""
        result = await handle_call_tool("search_vault", {"query": "test query"})
        assert len(result) == 1
        assert "No results" in result[0].text

    async def test_call_tool_with_none_arguments(self) -> None:
        result = await handle_call_tool("list_folders", None)
        assert len(result) == 1
        assert "Folders" in result[0].text
