"""MCP transport — serves both SSE and Streamable HTTP transports.

With FastMCP, the transport and auth middleware are handled internally.
This module creates a Starlette ASGI app that supports:

- **SSE transport** at ``/sse`` + ``/messages/`` (for Claude Code/Desktop)
- **Streamable HTTP** at ``/mcp`` (for OpenCode and newer MCP clients)

Both transports share the same underlying MCP server, OAuth provider,
and auth middleware.  The Google OAuth callback route is injected for
the auth delegation flow.
"""

import logging

from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware
from mcp.server.auth.routes import build_resource_metadata_url
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route

from obsidian_palace.auth.mcp_oauth import ObsidianPalaceOAuthProvider
from obsidian_palace.mcp.server import create_mcp_server

logger = logging.getLogger(__name__)


def create_mcp_app() -> Starlette:
    """Build the MCP Starlette app with SSE + Streamable HTTP transports.

    Returns:
        A Starlette ASGI application with both MCP transports, OAuth
        discovery/auth/token endpoints, and the Google callback route.
    """
    mcp, oauth_provider = create_mcp_server()

    # Get the FastMCP-built SSE app (includes all OAuth routes + SSE/message endpoints)
    sse_app = mcp.sse_app()

    # Add Streamable HTTP transport at /mcp (shares the same MCP server)
    _add_streamable_http_route(sse_app, mcp)

    # Add our Google OAuth callback route to the app
    _add_google_callback_route(sse_app, oauth_provider)

    return sse_app


def _add_streamable_http_route(app: Starlette, mcp: "FastMCP") -> None:  # noqa: F821
    """Add the Streamable HTTP endpoint at ``/mcp`` to an existing Starlette app.

    This creates a ``StreamableHTTPSessionManager`` that shares the same
    underlying ``MCPServer`` as the SSE transport.  The ``/mcp`` route is
    wrapped with the same ``RequireAuthMiddleware`` so OAuth tokens work
    identically on both transports.
    """
    session_manager = StreamableHTTPSessionManager(
        app=mcp._mcp_server,
        stateless=mcp.settings.stateless_http,
        json_response=mcp.settings.json_response,
        security_settings=mcp.settings.transport_security,
    )
    http_handler = StreamableHTTPASGIApp(session_manager)

    # Wrap with auth if configured (mirrors what streamable_http_app() does)
    if mcp._token_verifier and mcp.settings.auth and mcp.settings.auth.resource_server_url:
        resource_metadata_url = build_resource_metadata_url(
            mcp.settings.auth.resource_server_url,
        )
        required_scopes = mcp.settings.auth.required_scopes or []
        endpoint = RequireAuthMiddleware(http_handler, required_scopes, resource_metadata_url)
    else:
        endpoint = http_handler

    route = Route("/mcp", endpoint=endpoint)
    # Insert before catch-all routes so it takes precedence
    app.routes.insert(0, route)
    logger.info("Streamable HTTP transport added at /mcp")


def _add_google_callback_route(
    app: Starlette,
    oauth_provider: ObsidianPalaceOAuthProvider,
) -> None:
    """Add the /oauth2/callback route for Google OAuth redirect.

    This is the route Google redirects to after the user authorizes.
    We verify the Google token, check email, mint an MCP auth code,
    and redirect back to the MCP client's redirect_uri.
    """

    async def google_callback(request: Request) -> Response:
        """Handle Google OAuth callback."""
        error = request.query_params.get("error")
        if error:
            logger.error("Google OAuth error: %s", error)
            return Response(
                content=f"Google OAuth error: {error}",
                status_code=400,
            )

        code = request.query_params.get("code")
        state = request.query_params.get("state")

        if not code or not state:
            return Response(
                content="Missing code or state parameter",
                status_code=400,
            )

        try:
            redirect_url = await oauth_provider.handle_google_callback(
                code=code,
                state=state,
            )
            return RedirectResponse(url=redirect_url, status_code=302)
        except ValueError as exc:
            logger.error("OAuth callback failed: %s", exc)
            return Response(
                content=f"Authorization failed: {exc}",
                status_code=403,
            )

    # Insert the callback route at the beginning of the app's routes
    # so it takes precedence over the catch-all mount
    callback_route = Route("/oauth2/callback", endpoint=google_callback, methods=["GET"])
    app.routes.insert(0, callback_route)
