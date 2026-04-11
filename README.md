<div align="center">
  <img src="docs/assets/obsidian_palace.png" alt="ObsidianPalace" width="200">
</div>

# ObsidianPalace

MCP server that gives AI clients (Claude Desktop, Claude Code, claude.ai) full read/write/search access to your Obsidian vault.

## What It Does

ObsidianPalace bridges your Obsidian vault with AI via the [Model Context Protocol](https://modelcontextprotocol.io/). It runs as a single Docker container on a GCE instance (~$15/mo) and exposes five MCP tools:

| Tool | Description |
|------|-------------|
| `search_vault` | Semantic search across your vault using natural language |
| `read_note` | Read a note's full content by path |
| `write_note` | Write or update a note (with AI-assisted file placement) |
| `list_folders` | Browse the vault's folder structure |
| `list_notes` | List notes in a folder |

## How It Works

```
Claude Desktop / Code / Web
        │
        │  MCP over SSE (OAuth 2.1)
        ▼
┌─────────────────────────────────┐
│  ObsidianPalace (Docker)        │
│                                 │
│  nginx ─► FastAPI + MCP SDK     │
│           ├── MemPalace/ChromaDB│  ◄── semantic search
│           └── Anthropic API     │  ◄── AI file placement
│                                 │
│  ob sync --continuous           │  ◄── bidirectional Obsidian Sync
└─────────────────────────────────┘
```

- **Obsidian Headless CLI** (`ob sync --continuous`) keeps the vault in bidirectional sync with Obsidian Sync
- **MemPalace** (ChromaDB) provides semantic search over all vault content
- **AI Placement** uses Claude to decide where new notes belong in your vault structure
- **Google OAuth 2.0** authenticates requests via the MCP OAuth 2.1 specification
- **supervisord** manages nginx (SSL) + Node.js (sync) + Python (MCP server) in one container

## Quick Start

### Connect with Claude Code

```bash
claude mcp add obsidian-palace --transport sse https://your-domain.com/sse
```

### Local Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src tests
ruff format --check src tests
```

## Deploy Your Own

See the **[Setup Guide](docs/setup/index.md)** for a complete walkthrough covering:

1. GCP project creation
2. Google OAuth 2.0 client setup
3. Obsidian Sync credential extraction
4. Terraform configuration and deployment
5. DNS and SSL setup
6. Vault sync configuration on the server
7. Connecting Claude Desktop / Claude Code

**Prerequisites**: GCP account, Terraform, Obsidian Sync subscription, a domain, ~$15/mo.

## Project Structure

```
src/obsidian_palace/
├── app.py              # FastAPI application, health endpoint, MCP mount
├── config.py           # Pydantic Settings (OBSIDIAN_PALACE_ prefix)
├── auth/
│   └── mcp_oauth.py    # OAuth 2.1 server with Google delegation
├── mcp/
│   ├── server.py       # MCP tool definitions
│   └── transport.py    # SSE transport + OAuth callback
├── vault/
│   ├── operations.py   # Path-safe file read/write/list
│   └── placement.py    # AI-assisted file placement via Claude
└── search/
    ├── searcher.py     # MemPalace search wrapper
    ├── indexer.py      # Vault content indexer
    └── watcher.py      # File watcher for re-indexing

terraform/
├── environments/prod/  # Root module (backend, variables, outputs)
└── modules/obsidian_palace/  # Reusable module (GCE, disk, secrets, network)
```

## Tech Stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.12 |
| Framework | FastAPI + uvicorn |
| MCP | `mcp[server]` SDK, SSE transport |
| Search | MemPalace (ChromaDB) |
| Sync | obsidian-headless (`ob sync`) |
| Auth | Google OAuth 2.0 (MCP OAuth 2.1 spec) |
| IaC | Terraform (Terraform Cloud backend) |
| CI/CD | GitHub Actions |
| Container | Docker (supervisord, nginx, Node.js, Python) |
| Compute | GCE e2-small (~$15/mo) |

## Documentation

Full documentation is available at the [docs site](https://thewintershadow.github.io/ObsidianPalace/) or in the `docs/` directory:

- [Architecture](docs/architecture/index.md) -- system design, components, data flow
- [Setup Guide](docs/setup/index.md) -- deploy your own instance
- [Operations](docs/deployment/index.md) -- CI/CD, monitoring, maintenance
- [MCP Tools](docs/mcp-tools/index.md) -- detailed tool schemas and examples
- [API Reference](docs/api/index.md) -- Swagger UI and Python module docs

## License

MIT
