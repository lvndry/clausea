from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import config
from src.core.jwt import clerk_auth_service

logger = structlog.get_logger(service="auth_middleware")

# Routes that don't require authentication
WHITELISTED_ROUTES = {
    "/docs",
    "/health",
    "/health/detailed",
    "/health/ready",
    "/health/live",
    "/health/startup",
    "/openapi.json",
    "/users/tier-limits",
}

# Localhost addresses that are considered safe for development
LOCALHOST_ADDRESSES = ("127.0.0.1", "localhost", "::1")

# Service account identity for API key authentication
SERVICE_ACCOUNT_IDENTITY = {
    "user_id": "service_account",
    "email": "service@clausea.co",
    "service": True,
}


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self.logger = structlog.get_logger(service="auth_middleware")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Middleware to require authentication for all routes except whitelisted ones"""
        self._log_request(request)

        # Skip authentication for whitelisted routes
        if self._is_whitelisted(request):
            return await call_next(request)

        # Try different authentication methods
        auth_result = await self._authenticate(request)
        if auth_result:
            request.state.user = auth_result
            return await call_next(request)

        # No valid authentication found
        raise HTTPException(status_code=401, detail="Authorization required")

    def _is_whitelisted(self, request: Request) -> bool:
        """Check if the request path is whitelisted"""
        return request.url.path in WHITELISTED_ROUTES or request.method == "OPTIONS"

    async def _authenticate(self, request: Request) -> dict[str, Any] | None:
        """Try to authenticate the request using available methods"""
        # Method 1: Service API key (works in dev and production)
        if result := self._authenticate_service_api_key(request):
            return result

        # Method 2: Localhost bypass (development only)
        if result := self._authenticate_localhost(request):
            return result

        # Method 3: JWT token (standard user authentication)
        auth_header = request.headers.get("Authorization", "")
        if result := await self._authenticate_jwt(auth_header, request):
            return result

        return None

    def _authenticate_service_api_key(self, request: Request) -> dict[str, Any] | None:
        """Authenticate using service API key from X-CLAUSEA-API-KEY header"""
        api_key_header = request.headers.get("X-CLAUSEA-API-KEY", "")
        if not api_key_header:
            return None

        service_api_key = config.security.service_api_key
        if not service_api_key:
            return None

        if api_key_header == service_api_key:
            self.logger.info(
                "Service API key authentication successful",
                path=request.url.path,
                method=request.method,
            )
            return SERVICE_ACCOUNT_IDENTITY

        return None

    def _authenticate_localhost(self, request: Request) -> dict[str, Any] | None:
        """Allow localhost requests in development mode"""
        if not config.app.is_development:
            return None

        client_host = request.client.host if request.client else None
        if client_host not in LOCALHOST_ADDRESSES:
            return None

        self.logger.info(
            "Skipping authentication for localhost request (development mode)",
            path=request.url.path,
            method=request.method,
            client_host=client_host,
        )
        return {"user_id": "localhost_dev", "email": "dev@localhost", "dev": True}

    async def _authenticate_jwt(self, auth_header: str, request: Request) -> dict[str, Any] | None:
        """Authenticate using JWT token"""
        if not auth_header.startswith("Bearer "):
            self.logger.warning(
                "Missing or invalid authorization header",
                path=request.url.path,
                method=request.method,
            )
            return None

        try:
            token = auth_header.split(" ")[1]
            user_info: dict[str, Any] = await clerk_auth_service.verify_token(token)

            self.logger.info(
                "JWT authentication successful",
                email=user_info.get("email"),
                user_id=user_info.get("user_id"),
                path=request.url.path,
            )
            return user_info

        except Exception as e:
            self.logger.exception(
                "JWT authentication failed",
                error=str(e),
                path=request.url.path,
                method=request.method,
            )
            return None

    def _log_request(self, request: Request) -> None:
        """Log incoming request"""
        self.logger.info(
            "Incoming request",
            method=request.method,
            url=str(request.url),
            path=request.url.path,
        )
