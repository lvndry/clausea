"""Paddle webhook handlers for subscription events."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from motor.core import AgnosticDatabase

from src.core.database import get_db
from src.core.logging import get_logger
from src.models.user import UserTier
from src.services.paddle_service import paddle_service
from src.services.service_factory import create_user_service
from src.services.user_service import UserService

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def handle_subscription_created(
    event_data: dict[str, Any], db: AgnosticDatabase, user_service: UserService
) -> None:
    """Handle subscription.created event."""
    try:
        subscription = event_data.get("data", {})
        custom_data = subscription.get("custom_data", {})
        user_id = custom_data.get("user_id")

        if not user_id:
            logger.warning("No user_id in subscription.created event")
            return

        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            logger.error(f"User {user_id} not found for subscription.created")
            return

        # Determine tier from price_id
        items = subscription.get("items", [])
        if not items:
            logger.error("No items in subscription")
            return

        price_id = items[0].get("price", {}).get("id")
        tier = UserTier.FREE

        # Map price_id to tier
        from src.core.config import config

        if price_id in [
            config.paddle.price_individual_monthly,
            config.paddle.price_individual_annual,
        ]:
            tier = UserTier.INDIVIDUAL
        elif price_id in [
            config.paddle.price_business_monthly,
            config.paddle.price_business_annual,
        ]:
            tier = UserTier.BUSINESS

        # Update user
        user.tier = tier
        user.paddle_customer_id = subscription.get("customer_id")
        user.paddle_subscription_id = subscription.get("id")
        user.subscription_status = subscription.get("status")
        user.subscription_started_at = datetime.fromisoformat(
            subscription.get("started_at").replace("Z", "+00:00")
        )
        user.subscription_current_period_end = datetime.fromisoformat(
            subscription.get("current_billing_period", {}).get("ends_at").replace("Z", "+00:00")
        )

        await user_service.upsert_user(db, user)
        logger.info(f"User {user_id} upgraded to {tier.value}")

    except Exception as e:
        logger.error(f"Error handling subscription.created: {e}")
        raise


async def handle_subscription_updated(
    event_data: dict[str, Any], db: AgnosticDatabase, user_service: UserService
) -> None:
    """Handle subscription.updated event."""
    try:
        subscription = event_data.get("data", {})
        subscription_id = subscription.get("id")

        # Find user by subscription_id
        user = await user_service.get_user_by_subscription_id(db, subscription_id)
        if not user:
            logger.error(f"User not found for subscription {subscription_id}")
            return

        # Use the found user object directly
        user_obj = user

        # Update subscription status
        user_obj.subscription_status = subscription.get("status")
        user_obj.subscription_current_period_end = datetime.fromisoformat(
            subscription.get("current_billing_period", {}).get("ends_at").replace("Z", "+00:00")
        )

        await user_service.upsert_user(db, user_obj)
        logger.info(
            f"Updated subscription status for user {user_obj.id}: {user_obj.subscription_status}"
        )

    except Exception as e:
        logger.error(f"Error handling subscription.updated: {e}")
        raise


async def handle_subscription_canceled(
    event_data: dict[str, Any], db: AgnosticDatabase, user_service: UserService
) -> None:
    """Handle subscription.canceled event."""
    try:
        subscription = event_data.get("data", {})
        subscription_id = subscription.get("id")

        # Find user by subscription_id
        user = await user_service.get_user_by_subscription_id(db, subscription_id)
        if not user:
            logger.error(f"User not found for subscription {subscription_id}")
            return

        # Use the found user object directly
        user_obj = user

        # Downgrade to FREE tier
        user_obj.tier = UserTier.FREE
        user_obj.subscription_status = "canceled"
        user_obj.subscription_canceled_at = datetime.now()

        await user_service.upsert_user(db, user_obj)
        logger.info(f"User {user_obj.id} downgraded to FREE tier")

    except Exception as e:
        logger.error(f"Error handling subscription.canceled: {e}")
        raise


async def handle_subscription_past_due(
    event_data: dict[str, Any], db: AgnosticDatabase, user_service: UserService
) -> None:
    """Handle subscription.past_due event."""
    try:
        subscription = event_data.get("data", {})
        subscription_id = subscription.get("id")

        # Find user by subscription_id
        user = await user_service.get_user_by_subscription_id(db, subscription_id)
        if not user:
            logger.error(f"User not found for subscription {subscription_id}")
            return

        # Use the found user object directly
        user_obj = user

        # Update status to past_due
        user_obj.subscription_status = "past_due"

        await user_service.upsert_user(db, user_obj)
        logger.warning(f"Subscription past_due for user {user_obj.id}")

        # TODO: Send notification email to user

    except Exception as e:
        logger.error(f"Error handling subscription.past_due: {e}")
        raise


@router.post("/paddle")
async def paddle_webhook(
    request: Request,
    db: AgnosticDatabase = Depends(get_db),
    user_service: UserService = Depends(create_user_service),
) -> dict[str, str]:
    """
    Paddle webhook endpoint for subscription events.

    Handles events:
    - subscription.created
    - subscription.updated
    - subscription.canceled
    - subscription.past_due
    - subscription.paused
    - payment.succeeded
    - payment.failed
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        signature = request.headers.get("Paddle-Signature", "")

        # Verify webhook signature
        if not paddle_service.verify_webhook_signature(body, signature):
            logger.error("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse event data
        event_data: dict[str, Any] = json.loads(body)
        event_type = event_data.get("event_type")

        logger.info(f"Received Paddle webhook: {event_type}")

        # Handle different event types
        if event_type == "subscription.created":
            await handle_subscription_created(event_data, db, user_service)
        elif event_type == "subscription.updated":
            await handle_subscription_updated(event_data, db, user_service)
        elif event_type == "subscription.canceled":
            await handle_subscription_canceled(event_data, db, user_service)
        elif event_type == "subscription.past_due":
            await handle_subscription_past_due(event_data, db, user_service)
        elif event_type == "payment.succeeded":
            logger.info(f"Payment succeeded: {event_data}")
            # Just log for now, subscription.updated will handle status
        elif event_type == "payment.failed":
            logger.warning(f"Payment failed: {event_data}")
            # TODO: Send notification to user
        else:
            logger.info(f"Unhandled event type: {event_type}")

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed") from e
