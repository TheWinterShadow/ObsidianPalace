"""MCP OAuth 2.1 authorization server provider with Google OAuth delegation.

Implements the OAuthAuthorizationServerProvider protocol from the MCP SDK.
Claude Code and other MCP clients authenticate through our server, which
delegates actual user authentication to Google OAuth 2.0. Only Eli's
personal Google account is allowed.

Flow:
    1. MCP client dynamically registers via /register
    2. Client redirects user to /authorize
    3. We redirect to Google OAuth consent
    4. Google redirects back to /oauth2/callback
    5. We verify the Google token, check email, generate an MCP auth code
    6. We redirect to the MCP client's redirect_uri with the code
    7. Client exchanges code for our access/refresh tokens via /token
"""

import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from obsidian_palace.config import get_settings

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Token lifetimes
ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 86400 * 30  # 30 days
AUTH_CODE_TTL = 300  # 5 minutes


class ObsidianPalaceOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """OAuth provider that delegates authentication to Google.

    Single-user system: only the configured allowed_email can authenticate.
    All state is kept in-memory (acceptable for a single-user, single-process server).
    """

    def __init__(self) -> None:
        # In-memory stores — single-user, single-process, so this is fine.
        # On server restart, clients re-auth (which is expected behavior).
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}

        # Pending authorization state: maps our state param to
        # (client_id, original AuthorizationParams) so we can complete
        # the flow when Google redirects back.
        self._pending_auths: dict[str, tuple[str, AuthorizationParams]] = {}

    # ------------------------------------------------------------------
    # Dynamic Client Registration
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Look up a dynamically registered client."""
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Store a dynamically registered MCP client."""
        if client_info.client_id is None:
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="client_id is required",
            )
        logger.info(
            "Registering MCP client: %s (%s)",
            client_info.client_id,
            client_info.client_name or "unnamed",
        )
        self._clients[client_info.client_id] = client_info

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Redirect the user to Google OAuth for authentication.

        We generate a state token that maps back to the MCP client's
        authorization params so we can complete the redirect after
        Google authenticates the user.

        Returns:
            URL to redirect the user to (Google's OAuth consent page).
        """
        settings = get_settings()

        if not settings.google_client_id or not settings.google_client_secret:
            raise AuthorizeError(
                error="server_error",
                error_description="Google OAuth credentials not configured",
            )

        # Generate our own state to link Google callback back to this auth request
        google_state = secrets.token_urlsafe(32)
        self._pending_auths[google_state] = (client.client_id, params)

        # Build Google OAuth URL
        google_params = {
            "client_id": settings.google_client_id,
            "redirect_uri": f"{settings.server_url.rstrip('/')}/oauth2/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": google_state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(google_params)}"

    # ------------------------------------------------------------------
    # Google OAuth Callback (called from our FastAPI route)
    # ------------------------------------------------------------------

    async def handle_google_callback(
        self,
        code: str,
        state: str,
    ) -> str:
        """Process Google's OAuth callback and redirect to the MCP client.

        Args:
            code: Authorization code from Google.
            state: Our state param that maps to the pending auth request.

        Returns:
            Redirect URL to send the user back to the MCP client with our auth code.

        Raises:
            ValueError: If state is invalid or user is not authorized.
        """
        settings = get_settings()

        # Look up the pending auth request
        pending = self._pending_auths.pop(state, None)
        if pending is None:
            raise ValueError("Invalid or expired OAuth state")

        client_id, auth_params = pending

        # Exchange Google's code for tokens
        async with httpx.AsyncClient() as http:
            token_resp = await http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": f"{settings.server_url.rstrip('/')}/oauth2/callback",
                },
            )

        if token_resp.status_code != 200:
            logger.error("Google token exchange failed: %s", token_resp.text)
            raise ValueError("Failed to exchange Google authorization code")

        google_tokens = token_resp.json()
        google_access_token = google_tokens["access_token"]

        # Verify the user's identity
        async with httpx.AsyncClient() as http:
            userinfo_resp = await http.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {google_access_token}"},
            )

        if userinfo_resp.status_code != 200:
            raise ValueError("Failed to verify Google user identity")

        userinfo = userinfo_resp.json()
        email = userinfo.get("email", "")

        if email != settings.allowed_email:
            logger.warning("Unauthorized email attempted MCP auth: %s", email)
            raise ValueError(f"Email {email} is not authorized")

        logger.info("Google OAuth verified for: %s", email)

        # Generate our own MCP authorization code
        mcp_code = secrets.token_urlsafe(32)
        now = time.time()

        self._auth_codes[mcp_code] = AuthorizationCode(
            code=mcp_code,
            client_id=client_id,
            redirect_uri=auth_params.redirect_uri,
            redirect_uri_provided_explicitly=auth_params.redirect_uri_provided_explicitly,
            code_challenge=auth_params.code_challenge,
            scopes=auth_params.scopes or [],
            expires_at=now + AUTH_CODE_TTL,
            resource=auth_params.resource,
        )

        # Redirect back to MCP client
        return construct_redirect_uri(
            str(auth_params.redirect_uri),
            code=mcp_code,
            state=auth_params.state,
        )

    # ------------------------------------------------------------------
    # Token Exchange
    # ------------------------------------------------------------------

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        """Load a stored authorization code."""
        code = self._auth_codes.get(authorization_code)
        if code is None:
            return None
        if code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Exchange an authorization code for access + refresh tokens."""
        # Remove the used code (one-time use)
        self._auth_codes.pop(authorization_code.code, None)

        now = int(time.time())

        # Generate access token
        access_token_str = secrets.token_urlsafe(32)
        self._access_tokens[access_token_str] = AccessToken(
            token=access_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=now + ACCESS_TOKEN_TTL,
            resource=authorization_code.resource,
        )

        # Generate refresh token
        refresh_token_str = secrets.token_urlsafe(32)
        self._refresh_tokens[refresh_token_str] = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=now + REFRESH_TOKEN_TTL,
        )

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_token_str,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    # ------------------------------------------------------------------
    # Refresh Token
    # ------------------------------------------------------------------

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        """Load a stored refresh token."""
        token = self._refresh_tokens.get(refresh_token)
        if token is None:
            return None
        if token.client_id != client.client_id:
            return None
        # Check expiry (explicit None check — 0 is a valid expired timestamp)
        if token.expires_at is not None and token.expires_at < int(time.time()):
            self._refresh_tokens.pop(refresh_token, None)
            return None
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Rotate tokens: issue new access + refresh tokens."""
        # Revoke old refresh token
        self._refresh_tokens.pop(refresh_token.token, None)

        now = int(time.time())
        effective_scopes = scopes or refresh_token.scopes

        # New access token
        access_token_str = secrets.token_urlsafe(32)
        self._access_tokens[access_token_str] = AccessToken(
            token=access_token_str,
            client_id=client.client_id,
            scopes=effective_scopes,
            expires_at=now + ACCESS_TOKEN_TTL,
        )

        # New refresh token
        new_refresh_str = secrets.token_urlsafe(32)
        self._refresh_tokens[new_refresh_str] = RefreshToken(
            token=new_refresh_str,
            client_id=client.client_id,
            scopes=effective_scopes,
            expires_at=now + REFRESH_TOKEN_TTL,
        )

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL,
            refresh_token=new_refresh_str,
            scope=" ".join(effective_scopes) if effective_scopes else None,
        )

    # ------------------------------------------------------------------
    # Token Verification
    # ------------------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Validate a bearer token from an MCP request."""
        access_token = self._access_tokens.get(token)
        if access_token is None:
            return None
        # Check expiry (explicit None check — 0 is a valid expired timestamp)
        if access_token.expires_at is not None and access_token.expires_at < int(time.time()):
            self._access_tokens.pop(token, None)
            return None
        return access_token

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------

    async def revoke_token(
        self,
        token: AccessToken | RefreshToken,
    ) -> None:
        """Revoke an access or refresh token."""
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
            # Also revoke any refresh tokens for this client
            to_remove = [
                k for k, v in self._refresh_tokens.items() if v.client_id == token.client_id
            ]
            for k in to_remove:
                self._refresh_tokens.pop(k, None)
        elif isinstance(token, RefreshToken):
            self._refresh_tokens.pop(token.token, None)
            # Also revoke access tokens for this client
            to_remove = [
                k for k, v in self._access_tokens.items() if v.client_id == token.client_id
            ]
            for k in to_remove:
                self._access_tokens.pop(k, None)
