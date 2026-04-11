---
title: Connecting Clients
description: Connect MCP clients to your ObsidianPalace server.
icon: material/lan-connect
---

# Connecting Clients

Once your server is [deployed and verified](deployment.md#step-10-verify-the-deployment), connect your MCP clients. ObsidianPalace supports two transports:

| Transport | Endpoint | Used by |
|-----------|----------|---------|
| **SSE** (Server-Sent Events) | `/sse` | Claude Desktop, Claude Code, Claude iOS, claude.ai |
| **Streamable HTTP** | `/mcp` | OpenCode |

Both transports share the same authentication flow (MCP OAuth 2.1 with PKCE and dynamic client registration).

---

## Claude Code

Add the server to your Claude Code MCP configuration:

```bash
claude mcp add obsidian-palace --transport sse https://YOUR_DOMAIN/sse
```

Claude Code will automatically:

1. Discover the OAuth metadata endpoints
2. Dynamically register as an OAuth client
3. Open your browser for Google login
4. Exchange tokens and connect to the SSE stream

After authenticating, you should see the five ObsidianPalace tools available in Claude Code.

---

## Claude Desktop

Add to your Claude Desktop MCP config file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json title="claude_desktop_config.json"
{
  "mcpServers": {
    "obsidian-palace": {
      "transport": "sse",
      "url": "https://YOUR_DOMAIN/sse"
    }
  }
}
```

Restart Claude Desktop. It will prompt you to authenticate via Google OAuth on first connection.

---

## OpenCode

OpenCode uses Streamable HTTP transport (POST to a single endpoint), **not** SSE. Point it at `/mcp`, not `/sse`.

Add to `~/.config/opencode/opencode.json`:

```json title="opencode.json"
{
  "mcp": {
    "obsidian-palace": {
      "type": "remote",
      "url": "https://YOUR_DOMAIN/mcp"
    }
  }
}
```

OpenCode will auto-discover OAuth endpoints and prompt for authentication.

!!! warning "Wrong endpoint = 405"
    If you configure OpenCode with `/sse`, it will POST to that endpoint and get `405 Method Not Allowed`. The fix is to use `/mcp`.

---

## Other MCP Clients

Any MCP client that supports SSE transport and OAuth 2.1 (with dynamic client registration + PKCE) can connect. Use the appropriate endpoint:

- **SSE clients**: `https://YOUR_DOMAIN/sse`
- **Streamable HTTP clients**: `https://YOUR_DOMAIN/mcp`

The server handles OAuth discovery, dynamic client registration, authorization, and token exchange automatically. Clients just need to follow the standard MCP OAuth 2.1 flow:

1. Make an unauthenticated request → receive `401` with `WWW-Authenticate` header
2. Fetch `/.well-known/oauth-protected-resource`
3. Fetch `/.well-known/oauth-authorization-server`
4. Register dynamically via `POST /register`
5. Complete OAuth 2.1 with PKCE → receive access token
6. Connect with `Authorization: Bearer <token>`
