"""Sync Clausea user subscription state from Paddle."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.config import config
from src.core.logging import get_logger
from src.models.user import User, UserTier
from src.services.paddle_service import paddle_service
from src.services.service_factory import create_user_service

logger = get_logger(__name__)

_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "past_due"}


def resolve_tier_from_price_id(price_id: str | None) -> UserTier:
    """Map a Paddle price ID to a Clausea user tier."""
    if not price_id:
        return UserTier.FREE

    pro_price_ids = {
        config.paddle.price_pro_monthly,
        config.paddle.price_pro_annual,
    }
    if price_id in pro_price_ids:
        return UserTier.PRO

    return UserTier.FREE


def _parse_paddle_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def apply_subscription_data_to_user(user: User, subscription: dict[str, Any]) -> User:
    """Apply Paddle subscription payload fields onto a user record."""
    items = subscription.get("items", [])
    price_id = items[0].get("price", {}).get("id") if items else None
    status = subscription.get("status")
    tier = resolve_tier_from_price_id(price_id)

    if status in _ACTIVE_SUBSCRIPTION_STATUSES:
        user.tier = tier
    else:
        user.tier = UserTier.FREE

    user.paddle_customer_id = subscription.get("customer_id") or user.paddle_customer_id
    user.paddle_subscription_id = subscription.get("id") or user.paddle_subscription_id
    user.subscription_status = status
    user.subscription_started_at = (
        _parse_paddle_datetime(subscription.get("started_at")) or user.subscription_started_at
    )

    billing_period = subscription.get("current_billing_period") or {}
    user.subscription_current_period_end = (
        _parse_paddle_datetime(billing_period.get("ends_at"))
        or user.subscription_current_period_end
    )

    if status == "canceled":
        user.subscription_canceled_at = user.subscription_canceled_at or datetime.now()

    return user


def user_needs_subscription_sync(user: User) -> bool:
    """Return True when local subscription state may be stale."""
    return user.tier != UserTier.PRO and bool(user.paddle_subscription_id)


async def sync_user_subscription_from_paddle(
    db: AgnosticDatabase, user: User, *, recover_by_email: bool = False
) -> User:
    """Refresh a user's subscription fields from Paddle."""
    subscription_id = user.paddle_subscription_id

    if not subscription_id and recover_by_email:
        return await _recover_subscription_by_email(db, user)

    if not subscription_id:
        return user

    try:
        response = await paddle_service.get_subscription(subscription_id)
        subscription = response.get("data", {})
        if not subscription:
            logger.warning("No subscription data returned from Paddle for user %s", user.id)
            return user

        updated_user = apply_subscription_data_to_user(user, subscription)
        user_service = create_user_service()
        await user_service.upsert_user(db, updated_user)
        logger.info(
            "Synced subscription for user %s: tier=%s status=%s",
            user.id,
            updated_user.tier.value,
            updated_user.subscription_status,
        )
        return updated_user
    except Exception as e:
        logger.error("Failed to sync subscription for user %s: %s", user.id, e)
        return user


async def _recover_subscription_by_email(db: AgnosticDatabase, user: User) -> User:
    """Link a user to an active Paddle subscription using their account email."""
    if not user.email:
        return user

    try:
        customers_response = await paddle_service.list_customers_by_email(user.email)
        customers = customers_response.get("data", [])
        if not customers:
            return user

        for customer in customers:
            customer_id = customer.get("id")
            if not customer_id:
                continue

            subscriptions_response = await paddle_service.list_subscriptions_for_customer(
                customer_id
            )
            subscriptions = subscriptions_response.get("data", [])
            active_subscription = next(
                (
                    sub
                    for sub in subscriptions
                    if sub.get("status") in _ACTIVE_SUBSCRIPTION_STATUSES
                ),
                None,
            )
            if not active_subscription:
                continue

            updated_user = apply_subscription_data_to_user(user, active_subscription)
            updated_user.paddle_customer_id = customer_id
            user_service = create_user_service()
            await user_service.upsert_user(db, updated_user)
            logger.info(
                "Recovered Paddle subscription for user %s via email lookup",
                user.id,
            )
            return updated_user
    except Exception as e:
        logger.error("Failed to recover subscription for user %s: %s", user.id, e)

    return user
