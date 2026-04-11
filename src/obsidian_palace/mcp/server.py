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
    read_note,
    write_note,
)
from obsidian_palace.vault.placement import determine_placement

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
            "If no path is specified, AI determines the best location "
            "based on vault structure and content."
        ),
    )
    async def write_note_tool(
        content: str,
        path: str | None = None,
        title: str | None = None,
    ) -> str:
        """Write a note, optionally using AI placement."""
        if not path:
            path = await determine_placement(content, title=title)

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

    return mcp, oauth_provider
