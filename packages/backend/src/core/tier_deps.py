"""FastAPI dependencies for tier-based access control and usage limiting."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from motor.core import AgnosticDatabase

from src.core.database import get_db
from src.models.user import UserTier
from src.services.service_factory import create_user_service
from src.services.usage_service import UsageService

_BYPASS_USER_IDS = {"localhost_dev", "service_account"}


def _get_user_id(request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    if user and isinstance(user, dict):
        return user.get("user_id")
    return None


async def require_pro(
    request: Request,
    db: AgnosticDatabase = Depends(get_db),
) -> None:
    """Dependency that blocks unauthenticated requests (HTTP 401) and non-PRO users (HTTP 402)."""
    user_id = _get_user_id(request)
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
    """Dependency that enforces monthly usage limits per tier. Unauthenticated → HTTP 401."""
    user_id = _get_user_id(request)
    if user_id in _BYPASS_USER_IDS:
        return
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

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
    user_id = _get_user_id(request)
    if user_id in _BYPASS_USER_IDS or user_id is None:
        return
    await UsageService.increment_usage(db, user_id, endpoint=request.url.path)


async def get_user_tier(
    request: Request,
    db: AgnosticDatabase = Depends(get_db),
) -> UserTier:
    """Return the authenticated user's tier, defaulting to FREE."""
    user_id = _get_user_id(request)
    if user_id in _BYPASS_USER_IDS or user_id is None:
        return UserTier.FREE

    user_service = create_user_service()
    user = await user_service.get_user_by_id(db, user_id)
    if not user:
        return UserTier.FREE
    return user.tier
