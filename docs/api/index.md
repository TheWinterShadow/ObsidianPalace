---
title: API Reference
description: REST API documentation and Swagger UI for ObsidianPalace.
icon: material/code-tags
---

# API Reference

ObsidianPalace exposes a REST API alongside the MCP transport. FastAPI automatically generates interactive API documentation from the Python type annotations and docstrings.

## Live API Docs

When the server is running, interactive documentation is available at:

| Format | URL | Description |
|--------|-----|-------------|
| **Swagger UI** | `/docs` | Interactive API explorer with try-it-out |
| **ReDoc** | `/redoc` | Clean, readable API reference |
| **OpenAPI JSON** | `/openapi.json` | Raw OpenAPI 3.1 specification |

## REST Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/health` | Health check (version + status) | None |
| `GET` | `/docs` | Swagger UI | None |
| `GET` | `/redoc` | ReDoc documentation | None |
| `GET` | `/openapi.json` | OpenAPI specification | None |
| `GET` | `/sse` | MCP SSE transport | OAuth 2.0 |
| `POST` | `/mcp` | MCP Streamable HTTP transport | OAuth 2.0 |

## Health Check

```bash
curl https://YOUR_URL/health
```

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

## Authentication

The MCP endpoints require a Google OAuth 2.0 Bearer token:

```bash
# SSE transport
curl -H "Authorization: Bearer <token>" \
  https://YOUR_URL/sse

# Streamable HTTP transport
curl -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  https://YOUR_URL/mcp
```

The token is validated against Google's userinfo endpoint. Only the configured `allowed_email` is permitted access.

## Python Module Reference

Detailed auto-generated documentation for each Python module is available in the sidebar:

- [Application](app.md) -- FastAPI app, lifespan, health endpoint
- [Configuration](config.md) -- Pydantic Settings, environment variables
- [Auth / OAuth](auth/oauth.md) -- Google OAuth 2.0 token validation
- [MCP / Server](mcp/server.md) -- MCP tool definitions and handlers
- [MCP / Transport](mcp/transport.md) -- SSE + Streamable HTTP transport mounting
- [Vault / Operations](vault/operations.md) -- File read/write/list operations
- [Vault / Placement](vault/placement.md) -- AI-assisted file placement
- [Search / Searcher](search/searcher.md) -- MemPalace search wrapper
- [Search / Watcher](search/watcher.md) -- File watcher for re-indexing
