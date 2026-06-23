"""FastAPI dependencies for tier-based access control and usage limiting."""

from __future__ import annotations

import re
from typing import Any

from fastapi import Depends, HTTPException, Request
from motor.core import AgnosticDatabase

from src.core.database import get_db
from src.core.jwt import clerk_auth_service
from src.models.user import UserTier
from src.services.product_preview_usage import ProductPreviewUsageService
from src.services.service_factory import create_user_service
from src.services.usage_service import UsageService

_BYPASS_USER_IDS = {"localhost_dev", "service_account"}
_CRAWLER_UA_RE = re.compile(
    r"bot|crawl|spider|facebookexternalhit|Slackbot|Twitterbot|WhatsApp|"
    r"TelegramBot|LinkedInBot|discordbot|Applebot|preview|embed",
    re.IGNORECASE,
)
_METERED_PRODUCT_GET_RE = re.compile(
    r"^/products/(?:"
    r"[A-Za-z0-9][A-Za-z0-9_-]*"
    r"(?:/(?:overview|explainer|topics|documents(?:/[A-Za-z0-9][A-Za-z0-9_-]*/(?:extraction|deep-analysis))?))?"
    r")$"
)
_preview_usage_svc = ProductPreviewUsageService()


def _user_id_from_state(request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    if user and isinstance(user, dict):
        user_id = user.get("user_id")
        if isinstance(user_id, str) and user_id:
            return user_id
    return None


async def _resolve_request_user_id(request: Request) -> str | None:
    """Resolve the authenticated user ID from middleware state or Bearer JWT."""
    user_id = _user_id_from_state(request)
    if user_id:
        return user_id

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        return None

    try:
        payload: dict[str, Any] = await clerk_auth_service.verify_token(token)
    except HTTPException:
        return None
    except Exception:
        return None

    resolved = payload.get("sub") or payload.get("id")
    if isinstance(resolved, str) and resolved:
        request.state.user = {
            "user_id": resolved,
            "email": payload.get("email"),
            "name": payload.get("name"),
        }
        return resolved
    return None


def _get_client_ip(request: Request) -> str:
    if x_forwarded_for := request.headers.get("x-forwarded-for"):
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_crawler_request(request: Request) -> bool:
    user_agent = request.headers.get("user-agent", "")
    return bool(_CRAWLER_UA_RE.search(user_agent))


def _is_metered_product_get(request: Request) -> bool:
    return request.method == "GET" and bool(_METERED_PRODUCT_GET_RE.match(request.url.path))


def _should_increment_preview(request: Request) -> bool:
    """Count one preview view per page load (overview is the primary content gate)."""
    return request.url.path.endswith("/overview")


def _has_bearer_token(request: Request) -> bool:
    auth_header = request.headers.get("Authorization", "")
    return auth_header.startswith("Bearer ") and bool(auth_header.removeprefix("Bearer ").strip())


async def require_pro(
    request: Request,
    db: AgnosticDatabase = Depends(get_db),
) -> None:
    """Dependency that blocks unauthenticated requests (HTTP 401) and non-PRO users (HTTP 402)."""
    user_id = await _resolve_request_user_id(request)
    if user_id in _BYPASS_USER_IDS:
        return
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    user_service = create_user_service()
    user = await user_service.get_user_by_id(db, user_id)
    if not user or user.tier != UserTier.PRO:
        raise HTTPException(
            status_code=402,
            detail="This feature requires a Pro subscription.",
        )


async def check_usage_limit(
    request: Request,
    db: AgnosticDatabase = Depends(get_db),
) -> None:
    """Dependency that enforces usage limits for signed-in and anonymous users."""
    user_id = await _resolve_request_user_id(request)
    if user_id in _BYPASS_USER_IDS:
        return

    if user_id is None:
        if _has_bearer_token(request):
            raise HTTPException(
                status_code=401,
                detail="Session expired. Please sign in again.",
            )

        if not _is_metered_product_get(request) or _is_crawler_request(request):
            return

        preview_token = request.headers.get("X-Preview-Token", "").strip() or None
        client_ip = _get_client_ip(request)
        allowed, _ = await _preview_usage_svc.check_and_increment(
            db,
            token=preview_token,
            ip=client_ip,
            increment=_should_increment_preview(request),
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Free preview limit reached. Sign in for unlimited access.",
            )
        return

    user_service = create_user_service()
    user = await user_service.get_user_by_id(db, user_id)
    if user and user.tier == UserTier.PRO:
        return

    allowed, _ = await UsageService.check_usage_limit(db, user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Monthly usage limit reached. Upgrade to Pro for unlimited access.",
        )


async def increment_usage(
    request: Request,
    db: AgnosticDatabase = Depends(get_db),
) -> None:
    """Dependency that increments usage counter. Call AFTER successful response."""
    user_id = await _resolve_request_user_id(request)
    if user_id in _BYPASS_USER_IDS or user_id is None:
        return
    user_service = create_user_service()
    user = await user_service.get_user_by_id(db, user_id)
    if user and user.tier == UserTier.PRO:
        return

    await UsageService.increment_usage(db, user_id, endpoint=request.url.path)


async def get_user_tier(
    request: Request,
    db: AgnosticDatabase = Depends(get_db),
) -> UserTier:
    """Return the authenticated user's tier, defaulting to FREE."""
    user_id = await _resolve_request_user_id(request)
    if user_id in _BYPASS_USER_IDS or user_id is None:
        return UserTier.FREE

    user_service = create_user_service()
    user = await user_service.get_user_by_id(db, user_id)
    if not user:
        return UserTier.FREE
    return user.tier
