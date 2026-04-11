"""OAuth 2.0 token validation middleware.

Validates Google OAuth tokens on incoming requests and restricts
access to a single allowed email address (Eli's personal account).
"""

import logging

from fastapi import HTTPException, Request, status
from httpx import AsyncClient

from obsidian_palace.config import get_settings

logger = logging.getLogger(__name__)

GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


async def validate_oauth_token(request: Request) -> dict[str, str]:
    """Extract and validate the OAuth bearer token from the request.

    Calls Google's userinfo endpoint to verify the token and checks
    that the authenticated email matches the allowed email.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The Google userinfo payload (email, name, etc.).

    Raises:
        HTTPException: If the token is missing, invalid, or the email
            is not in the allowed list.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = auth_header.removeprefix("Bearer ")
    settings = get_settings()

    async with AsyncClient() as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

    if resp.status_code != 200:
        logger.warning("OAuth token validation failed: %s", resp.status_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OAuth token",
        )

    userinfo = resp.json()
    email = userinfo.get("email", "")

    if email != settings.allowed_email:
        logger.warning("Unauthorized email attempted access: %s", email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not authorized",
        )

    logger.info("Authenticated: %s", email)
    return userinfo
