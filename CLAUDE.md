# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

ObsidianPalace is a standalone MCP (Model Context Protocol) server that provides AI clients bidirectional access to an Obsidian vault. It syncs via `obsidian-headless`, indexes content with MemPalace (ChromaDB-backed semantic search), and exposes read/write/search tools over SSE and Streamable HTTP transports. Runs as a single Docker container on GCE e2-small (~$15/month).

See `AGENTS.md` for detailed architecture, constraints, and conventions.

## Commands

```bash
# Install (dev extras)
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v --tb=short

# Run a single test file
pytest tests/unit/test_vault_operations.py -v

# Lint
ruff check src tests

# Format check
ruff format --check src tests

# Auto-fix formatting
ruff format src tests

# Build Docker image
docker build -t obsidian-palace .

# Install pre-commit hooks
pre-commit install

# Run pre-commit manually
pre-commit run --all-files
```

## Architecture

Single Docker container with three supervisord-managed processes:

1. **nginx** — SSL termination (port 443 → 8080)
2. **Node.js sidecar** — `ob sync --continuous` (obsidian-headless), gated by `sync-guard.sh`
3. **Python MCP server** — FastAPI + MCP SDK on port 8080

**Request flow**: MCP client → nginx → FastAPI (`app.py`) → `mcp/transport.py` → `mcp/server.py` tools → `vault/operations.py` or `search/searcher.py`

**Key source files**:
- `src/obsidian_palace/config.py` — Pydantic Settings, `OBSIDIAN_PALACE_` env prefix
- `src/obsidian_palace/app.py` — FastAPI app, `/health`, MCP mount, lifespan (starts indexer + watcher)
- `src/obsidian_palace/mcp/server.py` — 5 MCP tool definitions (search, read, write, list_folders, list_notes)
- `src/obsidian_palace/mcp/transport.py` — SSE (`/sse`) + Streamable HTTP (`/mcp`) transports, OAuth callback
- `src/obsidian_palace/auth/mcp_oauth.py` — MCP OAuth 2.1 with Google delegation (single-user)
- `src/obsidian_palace/vault/operations.py` — Path-safe file I/O (path traversal protection)
- `src/obsidian_palace/vault/placement.py` — Claude API call to determine file path; falls back to `Inbox/`
- `src/obsidian_palace/search/` — ChromaDB indexer, MemPalace searcher wrapper, file watcher

**Infrastructure**: `terraform/environments/prod/` (root module) consumes `terraform/modules/obsidian_palace/` (GCE, persistent disk, firewall, Secret Manager). Backend: Terraform Cloud, org `TheWinterShadow`.

## Critical Rules

- **All vault operations must validate paths** — `operations.py` resolves and checks paths stay within `vault_path`. Never bypass.
- **MCP tool handlers return `list[types.TextContent]`** — Always `types.TextContent(type="text", text=...)`.
- **Python 3.12 target** — Do not use 3.13+ features. Docker pins 3.12.
- **ChromaDB/MemPalace search tests use stubs locally** — ChromaDB breaks on Python 3.14. Integration testing requires Docker.
- **`sync-guard.sh` enforces 3 gates** before `ob sync`: auth token exists, sync config exists, vault `.md` count ≥ 80% of last known good (prevents empty-vault propagation).
- **`ob login` and `ob sync-setup` are one-time interactive setup** — credentials persist to `/data/obsidian-config/` via symlinks.

## Tests

`tests/conftest.py` provides shared fixtures (`tmp_vault`, `test_settings`). All async tests use `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed). Tests are in `tests/unit/`.

## Terraform Conventions

- Directories over workspaces — `environments/prod/` consumes `modules/obsidian_palace/`
- Every variable and output has a `description`; sensitive ones marked `sensitive = true`
- Use validation blocks on variables and `check {}` blocks for post-deploy health checks
