"""MCP server definition and tool registration.

Uses FastMCP for ergonomic tool definitions with built-in OAuth support.
Exposes vault search, read, write, and listing tools over the Model
Context Protocol. Tool handlers delegate to the vault and search modules.
"""

import logging

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from obsidian_palace.auth.mcp_oauth import ObsidianPalaceOAuthProvider
from obsidian_palace.config import get_settings
from obsidian_palace.search.searcher import search
from obsidian_palace.vault.operations import (
    list_folders,
    list_notes,
    notes_for_date,
    read_note,
    write_note,
)

logger = logging.getLogger(__name__)


def create_mcp_server() -> tuple[FastMCP, ObsidianPalaceOAuthProvider]:
    """Create and configure the FastMCP server with OAuth.

    Returns:
        Tuple of (FastMCP server instance, OAuth provider for callback wiring).
    """
    settings = get_settings()
    oauth_provider = ObsidianPalaceOAuthProvider()

    server_url = settings.server_url.rstrip("/")

    mcp = FastMCP(
        name="obsidian-palace",
        instructions=(
            "ObsidianPalace provides access to an Obsidian vault. "
            "You can search notes semantically, read note contents, "
            "write new notes (with AI-assisted placement), and browse "
            "the folder structure."
        ),
        auth_server_provider=oauth_provider,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(server_url),
            resource_server_url=AnyHttpUrl(server_url),
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["vault:read", "vault:write", "vault:search"],
                default_scopes=["vault:read", "vault:write", "vault:search"],
            ),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=[],
        ),
        host=settings.host,
        port=settings.port,
    )

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------

    @mcp.tool(
        name="search_vault",
        description=(
            "Semantic search across the Obsidian vault using MemPalace. "
            "Returns relevant notes ranked by similarity."
        ),
    )
    async def search_vault(query: str, limit: int = 10) -> str:
        """Search the vault using semantic similarity."""
        results = await search(query, limit=limit)

        if not results:
            return f"No results found for: {query}"

        parts = [f"Found {len(results)} results for '{query}':\n"]
        for i, r in enumerate(results, 1):
            parts.append(f"---\n**{i}. {r.source_path}** (score: {r.score:.3f})\n{r.content[:300]}")
        return "\n".join(parts)

    @mcp.tool(
        name="read_note",
        description="Read the full content of a note from the Obsidian vault by path.",
    )
    async def read_note_tool(path: str) -> str:
        """Read a note's content by its vault-relative path."""
        return await read_note(path)

    @mcp.tool(
        name="write_note",
        description=(
            "Write or update a note in the Obsidian vault. "
            "All notes are written to the '00_Inbox' folder by default. "
            "Optionally include a title to name the note; otherwise it will be 'untitled.md'."
        ),
    )
    async def write_note_tool(
        content: str,
        title: str | None = None,
    ) -> str:
        """Write a note, optionally using AI placement."""
        path = f"00_Inbox/{title or 'untitled'}.md"

        written_path = await write_note(path, content)
        return f"Note written to: {path}\nAbsolute path: {written_path}"

    @mcp.tool(
        name="list_folders",
        description="List the folder structure of the Obsidian vault.",
    )
    async def list_folders_tool(path: str = "") -> str:
        """List vault folder structure."""
        folders = await list_folders(path)
        return f"Folders in '{path or '/'}':\n" + "\n".join(f"  {f}/" for f in folders)

    @mcp.tool(
        name="list_notes",
        description="List note files in a vault folder.",
    )
    async def list_notes_tool(path: str = "") -> str:
        """List notes in a vault folder."""
        notes = await list_notes(path)
        return f"Notes in '{path or '/'}':\n" + "\n".join(f"  {n}" for n in notes)

    @mcp.tool(
        name="notes_for_date",
        description=(
            "List all notes last modified on a specific date. Date must be in YYYY-MM-DD format."
        ),
    )
    async def notes_for_date_tool(date: str) -> str:
        """Return vault-relative paths of every note modified on the given date."""
        from datetime import date as date_type

        try:
            target = date_type.fromisoformat(date)
        except ValueError:
            return f"Invalid date '{date}'. Use YYYY-MM-DD format."

        results = await notes_for_date(target)
        if not results:
            return f"No notes found modified on {date}."
        return f"Notes modified on {date}:\n" + "\n".join(f"  {p}" for p in results)

    return mcp, oauth_provider
