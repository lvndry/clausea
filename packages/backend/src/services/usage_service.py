from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.constants import TIER_LIMITS
from src.core.logging import get_logger
from src.models.user import User
from src.services.service_factory import create_user_service

logger = get_logger(__name__)


class UsageService:
    """Service for handling user usage tracking and rate limiting"""

    # Monthly limits per tier
    TIER_LIMITS = TIER_LIMITS

    @staticmethod
    def get_current_month_key() -> str:
        """Get the current month in YYYY-MM format"""
        return datetime.now().strftime("%Y-%m")

    @staticmethod
    async def get_user_usage(db: AgnosticDatabase, user_id: str) -> User | None:
        """Get user with current usage information"""
        user_service = create_user_service()
        return await user_service.get_user_by_id(db, user_id)

    @staticmethod
    async def increment_usage(
        db: AgnosticDatabase, user_id: str, endpoint: str = "product_overview"
    ) -> bool:
        """
        Increment usage counter for the current month.
        Returns True if the request is allowed, False if limit exceeded.
        """
        try:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, user_id)
            if not user:
                logger.warning(f"User {user_id} not found for usage tracking")
                return True  # Allow request if user not found

            current_month = UsageService.get_current_month_key()
            current_usage = user.monthly_usage.get(current_month, 0)
            tier_limit = UsageService.TIER_LIMITS.get(user.tier, 0)

            # Check if user has exceeded their monthly limit
            if current_usage >= tier_limit:
                logger.info(
                    f"User {user_id} ({user.tier}) exceeded monthly limit: {current_usage}/{tier_limit}"
                )
                return False

            # Increment usage
            user.monthly_usage[current_month] = current_usage + 1
            user.updated_at = datetime.now()

            # Update user in database
            await user_service.upsert_user(db, user)

            logger.info(
                f"User {user_id} usage incremented: {current_usage + 1}/{tier_limit} for {current_month}"
            )
            return True

        except Exception as e:
            logger.error(f"Error incrementing usage for user {user_id}: {e}")
            return True  # Allow request on error to avoid blocking users

    @staticmethod
    async def check_usage_limit(db: AgnosticDatabase, user_id: str) -> tuple[bool, dict[str, Any]]:
        """
        Check if user has exceeded their usage limit.
        Returns (allowed, usage_info)
        """
        try:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, user_id)
            if not user:
                return True, {"limit": 0, "used": 0, "remaining": 0, "tier": "unknown"}

            current_month = UsageService.get_current_month_key()
            current_usage = user.monthly_usage.get(current_month, 0)
            tier_limit = UsageService.TIER_LIMITS.get(user.tier, 0)
            remaining = max(0, tier_limit - current_usage)

            usage_info = {
                "limit": tier_limit,
                "used": current_usage,
                "remaining": remaining,
                "tier": user.tier.value,
                "month": current_month,
            }

            return current_usage < tier_limit, usage_info

        except Exception as e:
            logger.error(f"Error checking usage limit for user {user_id}: {e}")
            return True, {"limit": 0, "used": 0, "remaining": 0, "tier": "unknown"}

    @staticmethod
    async def get_usage_summary(db: AgnosticDatabase, user_id: str) -> dict[str, Any]:
        """Get detailed usage summary for a user"""
        try:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, user_id)
            if not user:
                return {"error": "User not found"}

            current_month = UsageService.get_current_month_key()
            current_usage = user.monthly_usage.get(current_month, 0)
            tier_limit = UsageService.TIER_LIMITS.get(user.tier, 0)

            return {
                "user_id": user_id,
                "tier": user.tier.value,
                "current_month": current_month,
                "usage": {
                    "used": current_usage,
                    "limit": tier_limit,
                    "remaining": max(0, tier_limit - current_usage),
                    "percentage": (current_usage / tier_limit * 100) if tier_limit > 0 else 0,
                },
                "monthly_history": user.monthly_usage,
            }

        except Exception as e:
            logger.error(f"Error getting usage summary for user {user_id}: {e}")
            return {"error": str(e)}
