"""MCP server definition and tool registration.

Exposes vault search, read, write, and listing tools over the
Model Context Protocol. Tool handlers delegate to the vault and
search modules for actual file and index operations.
"""

import logging

import mcp.types as types
from mcp.server import Server

from obsidian_palace.search.searcher import search
from obsidian_palace.vault.operations import (
    list_folders,
    list_notes,
    read_note,
    write_note,
)
from obsidian_palace.vault.placement import determine_placement

logger = logging.getLogger(__name__)

server = Server("obsidian-palace")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Register all MCP tools available to consumers."""
    return [
        types.Tool(
            name="search_vault",
            description=(
                "Semantic search across the Obsidian vault using MemPalace. "
                "Returns relevant notes ranked by similarity."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="read_note",
            description="Read the full content of a note from the Obsidian vault by path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the note within the vault",
                    },
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="write_note",
            description=(
                "Write or update a note in the Obsidian vault. "
                "If no path is specified, AI determines the best location "
                "based on vault structure and content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Markdown content of the note",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative path in the vault. If omitted, "
                            "AI placement determines the location."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Note title (used for AI placement if path is omitted)",
                    },
                },
                "required": ["content"],
            },
        ),
        types.Tool(
            name="list_folders",
            description="List the folder structure of the Obsidian vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Subfolder to list (default: vault root)",
                        "default": "",
                    },
                },
            },
        ),
        types.Tool(
            name="list_notes",
            description="List note files in a vault folder.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Subfolder to list (default: vault root)",
                        "default": "",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Dispatch MCP tool calls to the appropriate handler."""
    args = arguments or {}
    logger.info("Tool call: %s(%s)", name, args)

    try:
        if name == "search_vault":
            return await _handle_search_vault(args)
        if name == "read_note":
            return await _handle_read_note(args)
        if name == "write_note":
            return await _handle_write_note(args)
        if name == "list_folders":
            return await _handle_list_folders(args)
        if name == "list_notes":
            return await _handle_list_notes(args)

        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return [types.TextContent(type="text", text=f"Error: {exc}")]


async def _handle_search_vault(args: dict) -> list[types.TextContent]:
    """Search the vault via MemPalace."""
    query = args["query"]
    limit = args.get("limit", 10)
    results = await search(query, limit=limit)

    if not results:
        return [types.TextContent(type="text", text=f"No results found for: {query}")]

    parts = [f"Found {len(results)} results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        parts.append(f"---\n**{i}. {r.source_path}** (score: {r.score:.3f})\n{r.content[:300]}")

    return [types.TextContent(type="text", text="\n".join(parts))]


async def _handle_read_note(args: dict) -> list[types.TextContent]:
    """Read a note from the vault."""
    path = args["path"]
    content = await read_note(path)
    return [types.TextContent(type="text", text=content)]


async def _handle_write_note(args: dict) -> list[types.TextContent]:
    """Write a note to the vault, optionally using AI placement."""
    content = args["content"]
    path = args.get("path")
    title = args.get("title")

    if not path:
        path = await determine_placement(content, title=title)

    written_path = await write_note(path, content)
    return [
        types.TextContent(
            type="text",
            text=f"Note written to: {path}\nAbsolute path: {written_path}",
        )
    ]


async def _handle_list_folders(args: dict) -> list[types.TextContent]:
    """List vault folder structure."""
    path = args.get("path", "")
    folders = await list_folders(path)
    text = f"Folders in '{path or '/'}':\n" + "\n".join(f"  {f}/" for f in folders)
    return [types.TextContent(type="text", text=text)]


async def _handle_list_notes(args: dict) -> list[types.TextContent]:
    """List notes in a vault folder."""
    path = args.get("path", "")
    notes = await list_notes(path)
    text = f"Notes in '{path or '/'}':\n" + "\n".join(f"  {n}" for n in notes)
    return [types.TextContent(type="text", text=text)]
