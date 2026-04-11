"""Tests for MCP server tool definitions and the OAuth provider."""

from pathlib import Path
from unittest.mock import patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from obsidian_palace.auth.mcp_oauth import ObsidianPalaceOAuthProvider
from obsidian_palace.mcp.server import create_mcp_server
from obsidian_palace.search.searcher import SearchResult


class TestCreateMcpServer:
    def test_creates_server_and_provider(self) -> None:
        mcp, provider = create_mcp_server()
        assert mcp.name == "obsidian-palace"
        assert isinstance(provider, ObsidianPalaceOAuthProvider)

    def test_registers_all_tools(self) -> None:
        mcp, _ = create_mcp_server()
        tools = mcp._tool_manager._tools
        names = set(tools.keys())
        assert names == {"search_vault", "read_note", "write_note", "list_folders", "list_notes"}


class TestToolFunctions:
    """Test the tool handler functions through FastMCP's tool manager.

    FastMCP wraps our tool functions. We call them through the tool manager
    to ensure they're properly registered and work end-to-end.
    """

    @pytest.fixture
    def mcp_server(self):
        mcp, _ = create_mcp_server()
        return mcp

    async def test_read_note(self, mcp_server, tmp_vault: Path) -> None:
        # call_tool returns the raw string from the tool function
        result = await mcp_server._tool_manager.call_tool(
            "read_note", {"path": "Projects/ObsidianPalace/design.md"}
        )
        assert isinstance(result, str)
        assert "MCP server for Obsidian vault access" in result

    async def test_read_note_not_found(self, mcp_server) -> None:
        with pytest.raises(ToolError, match="Note not found"):
            await mcp_server._tool_manager.call_tool("read_note", {"path": "nonexistent.md"})

    async def test_write_note(self, mcp_server, tmp_vault: Path) -> None:
        result = await mcp_server._tool_manager.call_tool(
            "write_note",
            {"content": "# Test\n\nTest content.", "path": "Inbox/mcp-test.md"},
        )
        assert isinstance(result, str)
        assert "Note written to" in result
        assert (tmp_vault / "Inbox" / "mcp-test.md").exists()

    async def test_write_note_ai_placement_fallback(self, mcp_server, tmp_vault: Path) -> None:
        """Without an API key, AI placement falls back to Inbox/."""
        result = await mcp_server._tool_manager.call_tool(
            "write_note",
            {"content": "# No path given\n\nShould go to Inbox.", "title": "fallback-test"},
        )
        assert isinstance(result, str)
        assert "Inbox/fallback-test.md" in result

    async def test_list_folders(self, mcp_server) -> None:
        result = await mcp_server._tool_manager.call_tool("list_folders", {"path": ""})
        assert isinstance(result, str)
        assert "Projects/" in result
        assert "Inbox/" in result

    async def test_list_notes(self, mcp_server) -> None:
        result = await mcp_server._tool_manager.call_tool("list_notes", {"path": "Inbox"})
        assert isinstance(result, str)
        assert "quick-note.md" in result

    async def test_search_vault_empty(self, mcp_server) -> None:
        with patch("obsidian_palace.mcp.server.search", return_value=[]):
            result = await mcp_server._tool_manager.call_tool(
                "search_vault", {"query": "test query"}
            )
        assert isinstance(result, str)
        assert "No results" in result

    async def test_search_vault_with_results(self, mcp_server) -> None:
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
            result = await mcp_server._tool_manager.call_tool("search_vault", {"query": "testing"})

        assert isinstance(result, str)
        assert "Found 2 results" in result
        assert "python-testing.md" in result
        assert "0.920" in result


class TestOAuthProvider:
    """Test the MCP OAuth provider."""

    @pytest.fixture
    def provider(self) -> ObsidianPalaceOAuthProvider:
        return ObsidianPalaceOAuthProvider()

    async def test_register_and_get_client(self, provider) -> None:
        from mcp.shared.auth import OAuthClientInformationFull

        client = OAuthClientInformationFull(
            client_id="test-client-123",
            client_secret="test-secret",
            redirect_uris=["http://localhost:3000/callback"],
        )
        await provider.register_client(client)

        retrieved = await provider.get_client("test-client-123")
        assert retrieved is not None
        assert retrieved.client_id == "test-client-123"

    async def test_get_nonexistent_client(self, provider) -> None:
        result = await provider.get_client("nonexistent")
        assert result is None

    async def test_load_nonexistent_access_token(self, provider) -> None:
        result = await provider.load_access_token("nonexistent")
        assert result is None

    async def test_access_token_expiry(self, provider) -> None:
        from mcp.server.auth.provider import AccessToken

        # Store a token that's already expired
        provider._access_tokens["expired-token"] = AccessToken(
            token="expired-token",
            client_id="test",
            scopes=[],
            expires_at=0,  # epoch = already expired
        )

        result = await provider.load_access_token("expired-token")
        assert result is None
        # Should also be cleaned up
        assert "expired-token" not in provider._access_tokens

    async def test_revoke_access_token(self, provider) -> None:
        from mcp.server.auth.provider import AccessToken, RefreshToken

        # Store tokens
        provider._access_tokens["at-1"] = AccessToken(
            token="at-1", client_id="client-a", scopes=[], expires_at=99999999999
        )
        provider._refresh_tokens["rt-1"] = RefreshToken(
            token="rt-1", client_id="client-a", scopes=[], expires_at=99999999999
        )

        # Revoking access token should also revoke refresh tokens for same client
        await provider.revoke_token(provider._access_tokens["at-1"])
        assert "at-1" not in provider._access_tokens
        assert "rt-1" not in provider._refresh_tokens
