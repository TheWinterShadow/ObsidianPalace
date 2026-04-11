# ObsidianPalace

MCP server bridging Obsidian vaults with AI via semantic search and bidirectional sync.

## Architecture

Single container running on GCE e2-small (~$15/mo) with:

- **Obsidian Headless CLI** (`ob sync --continuous`) — bidirectional vault sync via Obsidian Sync
- **MemPalace** — ChromaDB-backed semantic search over vault content
- **FastAPI + MCP over SSE** — exposes read/write/search tools to Claude and other MCP consumers
- **Google OAuth 2.0** — authenticates incoming requests (single-user, personal account only)
- **AI Placement** — uses Claude to determine where new files should go in the vault structure
- **supervisord** — manages Node.js sync + Python server in one container

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run locally
uvicorn obsidian_palace.app:app --reload

# Run tests
hatch run test

# Lint & format
hatch run dev:lint
hatch run dev:fmt
```

## Project Structure

```
src/obsidian_palace/
├── app.py           # FastAPI application
├── config.py        # Pydantic Settings
├── auth/
│   └── oauth.py     # Google OAuth 2.0 validation
├── mcp/
│   ├── server.py    # MCP tool definitions
│   └── transport.py # SSE transport mounting
├── vault/
│   ├── operations.py # File read/write/list
│   └── placement.py  # AI-assisted file placement
└── search/
    ├── searcher.py   # MemPalace search wrapper
    └── watcher.py    # File watcher for re-indexing
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_vault` | Semantic search across vault content |
| `read_note` | Read a note by path |
| `write_note` | Write/update a note (with optional AI placement) |
| `list_folders` | List vault folder structure |
