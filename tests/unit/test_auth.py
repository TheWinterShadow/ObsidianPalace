"""Tests for OAuth token validation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from obsidian_palace.auth.oauth import validate_oauth_token


class TestValidateOAuthToken:
    async def test_missing_auth_header(self) -> None:
        request = AsyncMock()
        request.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            await validate_oauth_token(request)
        assert exc_info.value.status_code == 401

    async def test_malformed_auth_header(self) -> None:
        request = AsyncMock()
        request.headers = {"Authorization": "Basic abc123"}
        with pytest.raises(HTTPException) as exc_info:
            await validate_oauth_token(request)
        assert exc_info.value.status_code == 401

    async def test_invalid_token_rejected(self) -> None:
        request = AsyncMock()
        request.headers = {"Authorization": "Bearer invalid-token"}

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("obsidian_palace.auth.oauth.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            with pytest.raises(HTTPException) as exc_info:
                await validate_oauth_token(request)
            assert exc_info.value.status_code == 401

    async def test_wrong_email_forbidden(self) -> None:
        request = AsyncMock()
        request.headers = {"Authorization": "Bearer valid-token"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "wrong@example.com"}

        with patch("obsidian_palace.auth.oauth.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            with pytest.raises(HTTPException) as exc_info:
                await validate_oauth_token(request)
            assert exc_info.value.status_code == 403

    async def test_valid_token_accepted(self) -> None:
        request = AsyncMock()
        request.headers = {"Authorization": "Bearer valid-token"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "test@example.com", "name": "Test User"}

        with patch("obsidian_palace.auth.oauth.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.get = AsyncMock(return_value=mock_response)

            result = await validate_oauth_token(request)
            assert result["email"] == "test@example.com"
