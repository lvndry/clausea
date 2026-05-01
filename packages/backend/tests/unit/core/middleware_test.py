"""Tests for AuthMiddleware.

Tests whitelisting, API key auth, localhost bypass, and JWT auth routing logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.middleware import (
    LOCALHOST_ADDRESSES,
    SERVICE_ACCOUNT_IDENTITY,
    WHITELISTED_ROUTES,
    AuthMiddleware,
)


@pytest.fixture
def middleware() -> AuthMiddleware:
    app = MagicMock()
    return AuthMiddleware(app)


def _make_request(
    path: str = "/products",
    method: str = "GET",
    headers: dict | None = None,
    client_host: str = "1.2.3.4",
) -> MagicMock:
    """Create a mock Request with the given attributes."""
    request = MagicMock()
    request.url.path = path
    request.method = method
    request.headers = headers or {}
    request.client = MagicMock()
    request.client.host = client_host
    request.state = MagicMock()
    return request


# ── Whitelisting ────────────────────────────────────────────────────


class TestWhitelisting:
    def test_whitelisted_routes_exist(self) -> None:
        assert "/health" in WHITELISTED_ROUTES
        assert "/docs" in WHITELISTED_ROUTES
        assert "/openapi.json" in WHITELISTED_ROUTES
        assert "/webhooks/paddle" in WHITELISTED_ROUTES
        assert "/contact" in WHITELISTED_ROUTES

    def test_whitelisted_route_detected(self, middleware: AuthMiddleware) -> None:
        request = _make_request(path="/health")
        assert middleware._is_whitelisted(request) is True

    def test_non_whitelisted_route(self, middleware: AuthMiddleware) -> None:
        request = _make_request(path="/products")
        assert middleware._is_whitelisted(request) is False

    def test_options_always_whitelisted(self, middleware: AuthMiddleware) -> None:
        request = _make_request(path="/products", method="OPTIONS")
        assert middleware._is_whitelisted(request) is True

    def test_all_health_endpoints_whitelisted(self, middleware: AuthMiddleware) -> None:
        for path in [
            "/health",
            "/health/detailed",
            "/health/ready",
            "/health/live",
            "/health/startup",
        ]:
            request = _make_request(path=path)
            assert middleware._is_whitelisted(request) is True, f"{path} should be whitelisted"


# ── Service API key auth ────────────────────────────────────────────


class TestServiceAPIKeyAuth:
    @patch("src.core.middleware.config")
    def test_valid_api_key(self, mock_config: MagicMock, middleware: AuthMiddleware) -> None:
        mock_config.security.service_api_key = "test-secret-key"
        request = _make_request(headers={"X-CLAUSEA-API-KEY": "test-secret-key"})
        result = middleware._authenticate_service_api_key(request)
        assert result == SERVICE_ACCOUNT_IDENTITY

    @patch("src.core.middleware.config")
    def test_invalid_api_key(self, mock_config: MagicMock, middleware: AuthMiddleware) -> None:
        mock_config.security.service_api_key = "test-secret-key"
        request = _make_request(headers={"X-CLAUSEA-API-KEY": "wrong-key"})
        result = middleware._authenticate_service_api_key(request)
        assert result is None

    @patch("src.core.middleware.config")
    def test_missing_api_key_header(
        self, mock_config: MagicMock, middleware: AuthMiddleware
    ) -> None:
        mock_config.security.service_api_key = "test-secret-key"
        request = _make_request(headers={})
        result = middleware._authenticate_service_api_key(request)
        assert result is None

    @patch("src.core.middleware.config")
    def test_no_configured_api_key(
        self, mock_config: MagicMock, middleware: AuthMiddleware
    ) -> None:
        mock_config.security.service_api_key = None
        request = _make_request(headers={"X-CLAUSEA-API-KEY": "some-key"})
        result = middleware._authenticate_service_api_key(request)
        assert result is None


# ── Localhost auth bypass ───────────────────────────────────────────


class TestLocalhostAuth:
    def test_localhost_addresses_defined(self) -> None:
        assert "127.0.0.1" in LOCALHOST_ADDRESSES
        assert "localhost" in LOCALHOST_ADDRESSES
        assert "::1" in LOCALHOST_ADDRESSES

    @patch("src.core.middleware.config")
    def test_localhost_bypass_in_dev(
        self, mock_config: MagicMock, middleware: AuthMiddleware
    ) -> None:
        mock_config.app.is_development = True
        request = _make_request(client_host="127.0.0.1")
        result = middleware._authenticate_localhost(request)
        assert result is not None
        assert result["user_id"] == "localhost_dev"

    @patch("src.core.middleware.config")
    def test_localhost_rejected_in_production(
        self, mock_config: MagicMock, middleware: AuthMiddleware
    ) -> None:
        mock_config.app.is_development = False
        request = _make_request(client_host="127.0.0.1")
        result = middleware._authenticate_localhost(request)
        assert result is None

    @patch("src.core.middleware.config")
    def test_non_localhost_rejected_in_dev(
        self, mock_config: MagicMock, middleware: AuthMiddleware
    ) -> None:
        mock_config.app.is_development = True
        request = _make_request(client_host="203.0.113.1")
        result = middleware._authenticate_localhost(request)
        assert result is None

    @patch("src.core.middleware.config")
    def test_no_client_info(self, mock_config: MagicMock, middleware: AuthMiddleware) -> None:
        mock_config.app.is_development = True
        request = _make_request()
        request.client = None
        result = middleware._authenticate_localhost(request)
        assert result is None


# ── JWT auth ────────────────────────────────────────────────────────


class TestJWTAuth:
    @pytest.mark.asyncio
    async def test_missing_bearer_prefix(self, middleware: AuthMiddleware) -> None:
        request = _make_request()
        result = await middleware._authenticate_jwt("Token xyz", request)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_auth_header(self, middleware: AuthMiddleware) -> None:
        request = _make_request()
        result = await middleware._authenticate_jwt("", request)
        assert result is None

    @pytest.mark.asyncio
    @patch("src.core.middleware.clerk_auth_service")
    async def test_valid_jwt(self, mock_clerk: MagicMock, middleware: AuthMiddleware) -> None:
        mock_clerk.verify_token = AsyncMock(
            return_value={"user_id": "user_123", "email": "user@example.com"}
        )
        request = _make_request()
        result = await middleware._authenticate_jwt("Bearer valid-token", request)
        assert result is not None
        assert result["user_id"] == "user_123"

    @pytest.mark.asyncio
    @patch("src.core.middleware.clerk_auth_service")
    async def test_invalid_jwt(self, mock_clerk: MagicMock, middleware: AuthMiddleware) -> None:
        mock_clerk.verify_token = AsyncMock(side_effect=Exception("Invalid token"))
        request = _make_request()
        result = await middleware._authenticate_jwt("Bearer bad-token", request)
        assert result is None


# ── Full dispatch flow ──────────────────────────────────────────────


class TestDispatchFlow:
    @pytest.mark.asyncio
    async def test_whitelisted_skips_auth(self, middleware: AuthMiddleware) -> None:
        request = _make_request(path="/health")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        await middleware.dispatch(request, call_next)
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("src.core.middleware.config")
    async def test_authenticated_request_proceeds(
        self, mock_config: MagicMock, middleware: AuthMiddleware
    ) -> None:
        mock_config.security.service_api_key = "key123"
        request = _make_request(
            path="/products",
            headers={"X-CLAUSEA-API-KEY": "key123"},
        )
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        await middleware.dispatch(request, call_next)
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("src.core.middleware.config")
    @patch("src.core.middleware.clerk_auth_service")
    async def test_unauthenticated_raises_401(
        self, mock_clerk: MagicMock, mock_config: MagicMock, middleware: AuthMiddleware
    ) -> None:
        mock_config.security.service_api_key = None
        mock_config.app.is_development = False
        request = _make_request(path="/products", headers={}, client_host="1.2.3.4")

        call_next = AsyncMock()
        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 401
