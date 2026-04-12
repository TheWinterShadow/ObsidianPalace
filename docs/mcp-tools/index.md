---
title: MCP Tools
description: Detailed reference for all ObsidianPalace MCP tools, their schemas, and usage examples.
icon: material/tools
---

# MCP Tools

ObsidianPalace exposes five tools via the Model Context Protocol. Any MCP-compatible client (Claude Desktop, Claude iOS, claude.ai, OpenCode) can invoke these tools after connecting via either transport.

## Connection

Connect to the MCP server using one of two transports:

| Transport | Endpoint | Description |
|-----------|----------|-------------|
| **SSE** | `https://YOUR_URL/sse` | Server-Sent Events — supported by most MCP clients |
| **Streamable HTTP** | `https://YOUR_URL/mcp` | Newer HTTP-based transport — used by OpenCode and other modern clients |

All requests require a valid Google OAuth 2.0 Bearer token in the `Authorization` header.

---

## search_vault

Semantic search across the Obsidian vault using MemPalace (ChromaDB). Returns relevant notes ranked by similarity score.

### Input Schema

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | `string` | Yes | -- | Natural language search query |
| `limit` | `integer` | No | `10` | Maximum number of results to return |

### Example

```json
{
  "name": "search_vault",
  "arguments": {
    "query": "kubernetes deployment strategies",
    "limit": 5
  }
}
```

### Response

Returns a formatted list of matching notes with their paths, similarity scores, and content previews (first 300 characters).

---

## read_note

Read the full markdown content of a note from the vault by its relative path.

### Input Schema

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | `string` | Yes | Relative path to the note within the vault |

### Example

```json
{
  "name": "read_note",
  "arguments": {
    "path": "Projects/ObsidianPalace/design-notes.md"
  }
}
```

### Response

Returns the full text content of the note.

!!! warning "Path traversal protection"
    All paths are resolved and validated to ensure they remain within the vault directory. Paths containing `../` or absolute paths that resolve outside the vault will be rejected.

---

## write_note

Write or update a note in the vault. If no `path` is provided, AI-assisted placement determines the best location based on the vault structure and note content.

### Input Schema

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | `string` | Yes | Markdown content of the note |
| `path` | `string` | No | Relative path in the vault. If omitted, AI determines the location. |
| `title` | `string` | No | Note title (used for AI placement context when path is omitted) |

### Example (explicit path)

```json
{
  "name": "write_note",
  "arguments": {
    "path": "Daily/2026-04-11.md",
    "content": "# April 11, 2026\n\nWorked on ObsidianPalace docs today."
  }
}
```

### Example (AI placement)

```json
{
  "name": "write_note",
  "arguments": {
    "title": "Terraform Best Practices",
    "content": "# Terraform Best Practices\n\n## Directories over workspaces\n..."
  }
}
```

### AI Placement Behavior

When `path` is omitted:

1. The server fetches the vault's current folder structure
2. Sends the folder tree, title, and content preview to Claude
3. Claude returns a recommended path (e.g., `Engineering/Infrastructure/terraform-best-practices.md`)
4. The note is written to that path, creating parent directories as needed

**Fallback**: If no Anthropic API key is configured or the API call fails, the note is written to `00_Inbox/{title}.md`.

---

## list_folders

List the folder structure of the vault at a given path.

### Input Schema

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | `string` | No | `""` (root) | Subfolder to list |

### Example

```json
{
  "name": "list_folders",
  "arguments": {
    "path": "Projects"
  }
}
```

### Response

Returns a newline-separated list of subdirectories at the given path.

---

## list_notes

List note files (`.md` files) in a vault folder.

### Input Schema

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | `string` | No | `""` (root) | Subfolder to list |

### Example

```json
{
  "name": "list_notes",
  "arguments": {
    "path": "Daily"
  }
}
```

### Response

Returns a newline-separated list of markdown files in the given folder.
