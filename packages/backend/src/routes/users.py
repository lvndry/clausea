from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.constants import TIER_DESCRIPTIONS, TIER_DISPLAY_NAMES, TIER_LIMITS
from src.core.database import get_db
from src.core.jwt import get_current_user
from src.models.clerkUser import ClerkUser
from src.models.user import User, UserTier
from src.services.service_factory import create_user_service
from src.services.usage_service import UsageService

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserRequest(BaseModel):
    email: str
    first_name: str | None = None
    last_name: str | None = None


class UpgradeTierRequest(BaseModel):
    tier: UserTier


@router.post("")
async def upsert_user(
    req: CreateUserRequest,
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Invalid user")

    user = User(
        id=current.user_id,
        email=req.email or current.email,
        first_name=req.first_name,
        last_name=req.last_name,
    )

    async with get_db() as db:
        user_service = create_user_service()
        await user_service.upsert_user(db, user)

    return {"status": "ok", "user_id": user.id}


@router.get("/me")
async def me(current: ClerkUser = Depends(get_current_user)) -> User:
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Invalid user")

    async with get_db() as db:
        user_service = create_user_service()
        user = await user_service.get_user_by_id(db, current.user_id)
        if user is None:
            # Create minimal user record on first access
            new_user = User(
                id=current.user_id,
                email=current.email,
            )
            await user_service.upsert_user(db, new_user)
            return new_user
        return user


@router.get("/usage")
async def get_usage(current: ClerkUser = Depends(get_current_user)) -> dict[str, Any]:
    """Get current user's usage information and limits"""
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Invalid user")

    async with get_db() as db:
        usage_summary: dict[str, Any] = await UsageService.get_usage_summary(db, current.user_id)
    return usage_summary


@router.get("/tier-limits")
async def get_tier_limits() -> dict[str, Any]:
    """Get tier limits and information for all available tiers"""
    tiers = []

    for tier in UserTier:
        tiers.append(
            {
                "tier": tier.value,
                "display_name": TIER_DISPLAY_NAMES[tier],
                "description": TIER_DESCRIPTIONS[tier],
                "monthly_limit": TIER_LIMITS[tier],
                "limit_type": "company_searches",
            }
        )

    return {"tiers": tiers, "limit_type": "company_searches", "period": "monthly"}


@router.post("/upgrade-tier")
async def upgrade_tier(
    req: UpgradeTierRequest,
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Upgrade user's tier"""
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Invalid user")

    async with get_db() as db:
        user_service = create_user_service()
        user = await user_service.get_user_by_id(db, current.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_tier = user.tier
        user.tier = req.tier
        await user_service.upsert_user(db, user)

    return {
        "success": True,
        "user_id": current.user_id,
        "old_tier": old_tier.value,
        "new_tier": req.tier.value,
        "upgraded_at": user.updated_at.isoformat(),
    }


class CompleteOnboardingRequest(BaseModel):
    completed: bool = True


@router.post("/complete-onboarding")
async def complete_onboarding_route(
    _: CompleteOnboardingRequest,
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Invalid user")

    async with get_db() as db:
        user_service = create_user_service()
        await user_service.set_user_onboarding_completed(db, current.user_id)
    return {"status": "ok"}
