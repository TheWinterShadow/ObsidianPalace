"""SSE transport for the MCP server.

With FastMCP, the transport and auth middleware are handled internally.
This module creates the Starlette ASGI app from FastMCP.sse_app() and
adds the Google OAuth callback route needed for the auth delegation flow.
"""

import logging

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route

from obsidian_palace.auth.mcp_oauth import ObsidianPalaceOAuthProvider
from obsidian_palace.mcp.server import create_mcp_server

logger = logging.getLogger(__name__)


def create_mcp_app() -> Starlette:
    """Build the MCP SSE Starlette app with OAuth.

    Returns:
        A Starlette ASGI application with MCP SSE transport, OAuth
        discovery/auth/token endpoints, and the Google callback route.
    """
    mcp, oauth_provider = create_mcp_server()

    # Get the FastMCP-built SSE app (includes all OAuth routes + SSE/message endpoints)
    sse_app = mcp.sse_app()

    # Add our Google OAuth callback route to the app
    _add_google_callback_route(sse_app, oauth_provider)

    return sse_app


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
