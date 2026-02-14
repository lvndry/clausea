"""Unit tests for JWT authentication service."""

from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.core.jwt import ClerkAuthService, get_current_user, get_optional_user
from src.models.clerkUser import ClerkUser


class TestClerkAuthService:
    """Test cases for ClerkAuthService."""

    @pytest.fixture
    def auth_service(self) -> ClerkAuthService:
        """Create ClerkAuthService instance for testing."""
        return ClerkAuthService()

    def test_auth_service_initialization(self, auth_service: ClerkAuthService) -> None:
        """Test ClerkAuthService initialization."""
        assert auth_service is not None
        assert hasattr(auth_service, "jwks_cache")
        assert hasattr(auth_service, "default_jwks_url")

    @pytest.mark.asyncio
    async def test_get_jwks_cached(self, auth_service: ClerkAuthService) -> None:
        """Test JWKS caching."""
        test_url = "https://test.example.com/.well-known/jwks.json"
        cached_jwks = {"keys": [{"kid": "cached_key"}]}
        auth_service.jwks_cache[test_url] = cached_jwks

        result = await auth_service.get_jwks(test_url)
        assert result == cached_jwks

    def test_auth_service_has_required_methods(self, auth_service: ClerkAuthService) -> None:
        """Test that ClerkAuthService has required methods."""
        assert hasattr(auth_service, "get_jwks")
        assert hasattr(auth_service, "verify_token")
        assert hasattr(auth_service, "extract_user_info")

    @pytest.mark.asyncio
    async def test_extract_user_info_success(
        self, auth_service: ClerkAuthService, mock_jwt_payload: dict[str, Any]
    ) -> None:
        """Test successful user info extraction."""
        with patch.object(auth_service, "verify_token", return_value=mock_jwt_payload):
            from fastapi.security import HTTPAuthorizationCredentials

            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test_token")

            user = await auth_service.extract_user_info(credentials)

            assert isinstance(user, ClerkUser)
            assert user.user_id == "test_user_123"
            assert user.email == "test@example.com"
            assert user.name == "Test User"

    @pytest.mark.asyncio
    async def test_extract_user_info_no_credentials(self, auth_service: ClerkAuthService) -> None:
        """Test user info extraction with no credentials."""
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.extract_user_info(None)

        assert exc_info.value.status_code == 401
        assert "Authorization header required" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_extract_user_info_missing_user_id(self, auth_service: ClerkAuthService) -> None:
        """Test user info extraction with missing user ID."""
        invalid_payload = {"email": "test@example.com", "name": "Test User"}

        with patch.object(auth_service, "verify_token", return_value=invalid_payload):
            from fastapi.security import HTTPAuthorizationCredentials

            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test_token")

            with pytest.raises(HTTPException) as exc_info:
                await auth_service.extract_user_info(credentials)

            assert exc_info.value.status_code == 401
            assert "Invalid token: missing user ID" in str(exc_info.value.detail)


class TestJWTDependencies:
    """Test cases for JWT dependency functions."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_clerk_user: ClerkUser) -> None:
        """Test successful current user retrieval."""
        with patch(
            "src.core.jwt.clerk_auth_service.extract_user_info", return_value=mock_clerk_user
        ):
            from fastapi.security import HTTPAuthorizationCredentials

            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test_token")

            user = await get_current_user(credentials)
            assert user == mock_clerk_user

    @pytest.mark.asyncio
    async def test_get_optional_user_authenticated(self, mock_clerk_user: ClerkUser) -> None:
        """Test optional user retrieval when authenticated."""
        with patch(
            "src.core.jwt.clerk_auth_service.extract_user_info", return_value=mock_clerk_user
        ):
            from fastapi.security import HTTPAuthorizationCredentials

            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test_token")

            user = await get_optional_user(credentials)
            assert user == mock_clerk_user

    @pytest.mark.asyncio
    async def test_get_optional_user_not_authenticated(self) -> None:
        """Test optional user retrieval when not authenticated."""
        with patch(
            "src.core.jwt.clerk_auth_service.extract_user_info",
            side_effect=HTTPException(status_code=401, detail="Unauthorized"),
        ):
            user = await get_optional_user(None)
            assert user is None

    @pytest.mark.asyncio
    async def test_get_optional_user_no_credentials(self) -> None:
        """Test optional user retrieval with no credentials."""
        user = await get_optional_user(None)
        assert user is None
