"""Tests for MCP server tool definitions and the OAuth provider."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from mcp.server.auth.provider import AccessToken, RefreshToken
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.auth import OAuthClientInformationFull

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
        assert names == {
            "coding_guidance",
            "search_vault",
            "read_note",
            "write_note",
            "list_folders",
            "list_notes",
            "notes_for_date",
        }


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
            {"content": "# Test\n\nTest content.", "title": "mcp-test"},
        )
        assert isinstance(result, str)
        assert "Note written to" in result
        assert (tmp_vault / "00_Inbox" / "mcp-test.md").exists()

    async def test_write_note_ai_placement_fallback(self, mcp_server, tmp_vault: Path) -> None:
        """Without an API key, AI placement falls back to 00_Inbox/."""
        result = await mcp_server._tool_manager.call_tool(
            "write_note",
            {"content": "# No path given\n\nShould go to 00_Inbox.", "title": "fallback-test"},
        )
        assert isinstance(result, str)
        assert "00_Inbox/fallback-test.md" in result

    async def test_list_folders(self, mcp_server) -> None:
        result = await mcp_server._tool_manager.call_tool("list_folders", {"path": ""})
        assert isinstance(result, str)
        assert "Projects/" in result
        assert "00_Inbox/" in result

    async def test_list_notes(self, mcp_server) -> None:
        result = await mcp_server._tool_manager.call_tool("list_notes", {"path": "00_Inbox"})
        assert isinstance(result, str)
        assert "quick-note.md" in result

    async def test_notes_for_date_found(self, mcp_server, tmp_vault: Path) -> None:
        import os
        import time
        from datetime import date

        target = tmp_vault / "00_Inbox" / "quick-note.md"
        today = date.today()
        ts = time.mktime(today.timetuple())
        os.utime(target, (ts, ts))

        result = await mcp_server._tool_manager.call_tool(
            "notes_for_date", {"date": today.isoformat()}
        )
        assert isinstance(result, str)
        assert "00_Inbox/quick-note.md" in result

    async def test_notes_for_date_none_found(self, mcp_server) -> None:
        result = await mcp_server._tool_manager.call_tool("notes_for_date", {"date": "1970-01-01"})
        assert "No notes found" in result

    async def test_notes_for_date_invalid(self, mcp_server) -> None:
        result = await mcp_server._tool_manager.call_tool("notes_for_date", {"date": "not-a-date"})
        assert "Invalid date" in result

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
    def provider(self, tmp_path: Path) -> ObsidianPalaceOAuthProvider:
        return ObsidianPalaceOAuthProvider(state_file=tmp_path / "oauth_state.json")

    async def test_register_and_get_client(self, provider) -> None:
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


class TestOAuthPersistence:
    """Test that OAuth state survives provider restarts (file-backed store)."""

    async def test_registered_client_survives_restart(self, tmp_path: Path) -> None:
        state_file = tmp_path / "oauth_state.json"

        # Register a client, then create a new provider from the same file
        provider1 = ObsidianPalaceOAuthProvider(state_file=state_file)
        client = OAuthClientInformationFull(
            client_id="persistent-client",
            client_secret="secret",
            redirect_uris=["http://localhost:3000/callback"],
        )
        await provider1.register_client(client)

        # "Restart" — new provider instance loading from disk
        provider2 = ObsidianPalaceOAuthProvider(state_file=state_file)
        retrieved = await provider2.get_client("persistent-client")
        assert retrieved is not None
        assert retrieved.client_id == "persistent-client"

    async def test_tokens_survive_restart(self, tmp_path: Path) -> None:
        state_file = tmp_path / "oauth_state.json"

        provider1 = ObsidianPalaceOAuthProvider(state_file=state_file)
        provider1._access_tokens["survivor"] = AccessToken(
            token="survivor",
            client_id="test",
            scopes=["vault:read"],
            expires_at=99999999999,
        )
        provider1._refresh_tokens["refresh-survivor"] = RefreshToken(
            token="refresh-survivor",
            client_id="test",
            scopes=["vault:read"],
            expires_at=99999999999,
        )
        provider1._save_state()

        # "Restart"
        provider2 = ObsidianPalaceOAuthProvider(state_file=state_file)
        at = await provider2.load_access_token("survivor")
        assert at is not None
        assert at.client_id == "test"

        # Refresh token too
        assert "refresh-survivor" in provider2._refresh_tokens

    async def test_expired_tokens_pruned_on_load(self, tmp_path: Path) -> None:
        state_file = tmp_path / "oauth_state.json"

        provider1 = ObsidianPalaceOAuthProvider(state_file=state_file)
        provider1._access_tokens["dead-token"] = AccessToken(
            token="dead-token",
            client_id="test",
            scopes=[],
            expires_at=0,  # already expired
        )
        provider1._save_state()

        # "Restart" — expired token should be pruned
        provider2 = ObsidianPalaceOAuthProvider(state_file=state_file)
        assert "dead-token" not in provider2._access_tokens

    async def test_corrupt_state_file_handled_gracefully(self, tmp_path: Path) -> None:
        state_file = tmp_path / "oauth_state.json"
        state_file.write_text("not valid json {{{")

        # Should not raise, just start fresh
        provider = ObsidianPalaceOAuthProvider(state_file=state_file)
        assert len(provider._clients) == 0

    async def test_missing_state_file_starts_fresh(self, tmp_path: Path) -> None:
        state_file = tmp_path / "nonexistent" / "oauth_state.json"
        provider = ObsidianPalaceOAuthProvider(state_file=state_file)
        assert len(provider._clients) == 0

    async def test_state_file_written_as_valid_json(self, tmp_path: Path) -> None:
        state_file = tmp_path / "oauth_state.json"
        provider = ObsidianPalaceOAuthProvider(state_file=state_file)

        client = OAuthClientInformationFull(
            client_id="json-check",
            client_secret="secret",
            redirect_uris=["http://localhost/cb"],
        )
        await provider.register_client(client)

        # File should be valid JSON
        data = json.loads(state_file.read_text())
        assert "clients" in data
        assert "json-check" in data["clients"]
