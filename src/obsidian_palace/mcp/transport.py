"""SSE transport for the MCP server.

Mounts the MCP server onto the FastAPI app using Server-Sent Events,
which is the transport protocol required by Claude Custom Connectors.
"""

import logging

from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from obsidian_palace.auth.oauth import validate_oauth_token
from obsidian_palace.mcp.server import server

logger = logging.getLogger(__name__)

sse_transport = SseServerTransport("/mcp/messages/")


async def handle_sse(request: Request) -> Response:
    """Handle incoming SSE connection for MCP.

    Validates the OAuth token before establishing the SSE stream.
    """
    await validate_oauth_token(request)

    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options(),
        )
    return Response()


async def handle_messages(request: Request) -> None:
    """Handle incoming MCP messages over the SSE channel."""
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)


def create_mcp_routes() -> Mount:
    """Create the Starlette Mount with MCP SSE routes.

    Returns:
        A Starlette Mount containing the SSE and message endpoints.
    """
    return Mount(
        "/mcp",
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
    )
