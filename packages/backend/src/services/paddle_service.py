"""Paddle payment service for subscription management."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from src.core.config import config
from src.core.logging import get_logger

logger = get_logger(__name__)


class PaddleService:
    """Service for interacting with Paddle's Billing API."""

    BASE_URL_SANDBOX = "https://sandbox-api.paddle.com"
    BASE_URL_PRODUCTION = "https://api.paddle.com"

    def __init__(self) -> None:
        """Initialize Paddle service with API credentials."""
        self.api_key = config.paddle.api_key
        self.webhook_secret = config.paddle.webhook_secret
        self.environment = config.paddle.environment
        self.base_url = (
            self.BASE_URL_PRODUCTION if self.environment == "production" else self.BASE_URL_SANDBOX
        )

        if not self.api_key:
            logger.warning("Paddle API key not configured")

    def _get_headers(self) -> dict[str, str]:
        """Get headers for Paddle API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_checkout_session(
        self,
        price_id: str,
        customer_email: str,
        customer_id: str | None = None,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a Paddle checkout session.

        Args:
            price_id: Paddle price ID for the subscription
            customer_email: Customer email address
            customer_id: Optional existing Paddle customer ID
            success_url: URL to redirect after successful checkout
            cancel_url: URL to redirect if checkout is canceled

        Returns:
            Checkout session data including checkout URL
        """
        try:
            payload: dict[str, Any] = {
                "items": [{"price_id": price_id, "quantity": 1}],
            }

            if customer_id:
                payload["customer_id"] = customer_id
            else:
                payload["customer_email"] = customer_email

            if success_url:
                payload["custom_data"] = {"success_url": success_url}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/checkout/sessions",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                logger.info(f"Created checkout session for {customer_email}")
                return data  # type: ignore

        except Exception as e:
            logger.error(f"Error creating checkout session: {e}")
            raise

    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """
        Get subscription details.

        Args:
            subscription_id: Paddle subscription ID

        Returns:
            Subscription data
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/subscriptions/{subscription_id}",
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()  # type: ignore

        except Exception as e:
            logger.error(f"Error getting subscription {subscription_id}: {e}")
            raise

    async def cancel_subscription(
        self, subscription_id: str, effective_from: str = "next_billing_period"
    ) -> dict[str, Any]:
        """
        Cancel a subscription.

        Args:
            subscription_id: Paddle subscription ID
            effective_from: When to cancel - "next_billing_period" or "immediately"

        Returns:
            Updated subscription data
        """
        try:
            payload = {"effective_from": effective_from}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/subscriptions/{subscription_id}/cancel",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.info(f"Canceled subscription {subscription_id}")
                return response.json()  # type: ignore

        except Exception as e:
            logger.error(f"Error canceling subscription {subscription_id}: {e}")
            raise

    async def pause_subscription(self, subscription_id: str) -> dict[str, Any]:
        """
        Pause a subscription.

        Args:
            subscription_id: Paddle subscription ID

        Returns:
            Updated subscription data
        """
        try:
            payload = {"effective_from": "next_billing_period"}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/subscriptions/{subscription_id}/pause",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.info(f"Paused subscription {subscription_id}")
                return response.json()  # type: ignore

        except Exception as e:
            logger.error(f"Error pausing subscription {subscription_id}: {e}")
            raise

    async def resume_subscription(self, subscription_id: str) -> dict[str, Any]:
        """
        Resume a paused subscription.

        Args:
            subscription_id: Paddle subscription ID

        Returns:
            Updated subscription data
        """
        try:
            payload = {"effective_from": "immediately"}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/subscriptions/{subscription_id}/resume",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.info(f"Resumed subscription {subscription_id}")
                return response.json()  # type: ignore

        except Exception as e:
            logger.error(f"Error resuming subscription {subscription_id}: {e}")
            raise

    async def get_customer_portal_session(self, customer_id: str) -> dict[str, Any]:
        """
        Create a customer portal session for billing management.

        Args:
            customer_id: Paddle customer ID

        Returns:
            Portal session data including portal URL
        """
        try:
            payload = {"customer_id": customer_id}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/customer-portal-sessions",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.info(f"Created portal session for customer {customer_id}")
                return response.json()  # type: ignore

        except Exception as e:
            logger.error(f"Error creating portal session for {customer_id}: {e}")
            raise

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Paddle webhook signature.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature from Paddle-Signature header

        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            logger.error("Webhook secret not configured")
            return False

        try:
            # Paddle uses HMAC SHA256
            expected_signature = hmac.new(
                self.webhook_secret.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False


# Global instance
paddle_service = PaddleService()
