"""Subscription management API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.core.database import get_db
from src.core.jwt import get_current_user
from src.core.logging import get_logger
from src.models.clerkUser import ClerkUser
from src.services.paddle_service import paddle_service
from src.services.service_factory import create_user_service

logger = get_logger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class CheckoutRequest(BaseModel):
    """Request to create a checkout session."""

    price_id: str
    success_url: str | None = None
    cancel_url: str | None = None


@router.post("/checkout")
async def create_checkout(
    req: CheckoutRequest,
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Create a Paddle checkout session for subscription purchase.

    Args:
        req: Checkout request with price_id and optional redirect URLs
        current: Authenticated user from Clerk

    Returns:
        Checkout session with URL to redirect user
    """
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        async with get_db() as db:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, current.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

        # Create checkout session
        session = await paddle_service.create_checkout_session(
            price_id=req.price_id,
            customer_email=user.email,
            customer_id=user.paddle_customer_id,
            success_url=req.success_url,
            cancel_url=req.cancel_url,
        )

        # Extract checkout URL from session
        checkout_url = session.get("data", {}).get("url")
        if not checkout_url:
            raise HTTPException(status_code=500, detail="Failed to create checkout session")

        return {
            "checkout_url": checkout_url,
            "session_id": session.get("data", {}).get("id"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating checkout: {e}")
        raise HTTPException(status_code=500, detail="Checkout creation failed") from e


@router.get("/me")
async def get_my_subscription(
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Get current user's subscription details.

    Returns:
        Subscription information including tier, status, and billing period
    """
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        async with get_db() as db:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, current.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

        subscription_data: dict[str, Any] = {
            "tier": user.tier.value,
            "status": user.subscription_status or "inactive",
            "paddle_customer_id": user.paddle_customer_id,
            "paddle_subscription_id": user.paddle_subscription_id,
        }

        if user.subscription_started_at:
            subscription_data["started_at"] = user.subscription_started_at.isoformat()

        if user.subscription_current_period_end:
            subscription_data["current_period_end"] = (
                user.subscription_current_period_end.isoformat()
            )

        if user.subscription_canceled_at:
            subscription_data["canceled_at"] = user.subscription_canceled_at.isoformat()

        return subscription_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve subscription") from e


@router.post("/cancel")
async def cancel_subscription(
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Cancel current user's subscription (effective at end of billing period).

    Returns:
        Updated subscription status
    """
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        async with get_db() as db:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, current.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if not user.paddle_subscription_id:
                raise HTTPException(status_code=400, detail="No active subscription")

        # Cancel subscription in Paddle
        result = await paddle_service.cancel_subscription(
            user.paddle_subscription_id, effective_from="next_billing_period"
        )

        logger.info(f"User {current.user_id} canceled subscription")

        return {
            "success": True,
            "message": "Subscription will cancel at end of billing period",
            "subscription": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error canceling subscription: {e}")
        raise HTTPException(status_code=500, detail="Subscription cancellation failed") from e


@router.post("/pause")
async def pause_subscription(
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Pause current user's subscription.

    Returns:
        Updated subscription status
    """
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        async with get_db() as db:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, current.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if not user.paddle_subscription_id:
                raise HTTPException(status_code=400, detail="No active subscription")

        # Pause subscription in Paddle
        result = await paddle_service.pause_subscription(user.paddle_subscription_id)

        logger.info(f"User {current.user_id} paused subscription")

        return {"success": True, "message": "Subscription paused", "subscription": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing subscription: {e}")
        raise HTTPException(status_code=500, detail="Subscription pause failed") from e


@router.post("/resume")
async def resume_subscription(
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Resume a paused subscription.

    Returns:
        Updated subscription status
    """
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        async with get_db() as db:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, current.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if not user.paddle_subscription_id:
                raise HTTPException(status_code=400, detail="No subscription to resume")

        # Resume subscription in Paddle
        result = await paddle_service.resume_subscription(user.paddle_subscription_id)

        logger.info(f"User {current.user_id} resumed subscription")

        return {
            "success": True,
            "message": "Subscription resumed",
            "subscription": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming subscription: {e}")
        raise HTTPException(status_code=500, detail="Subscription resume failed") from e


@router.get("/portal")
async def get_billing_portal(
    current: ClerkUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Get Paddle billing portal URL for self-service subscription management.

    Returns:
        Portal URL to redirect user
    """
    if not current.user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        async with get_db() as db:
            user_service = create_user_service()
            user = await user_service.get_user_by_id(db, current.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            if not user.paddle_customer_id:
                raise HTTPException(status_code=400, detail="No Paddle customer record found")

        # Get portal session
        portal = await paddle_service.get_customer_portal_session(user.paddle_customer_id)

        portal_url = portal.get("data", {}).get("url")
        if not portal_url:
            raise HTTPException(status_code=500, detail="Failed to create portal session")

        return {"portal_url": portal_url}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting billing portal: {e}")
        raise HTTPException(status_code=500, detail="Portal creation failed") from e
