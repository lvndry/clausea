"""Indexation notification service.

Allows users to subscribe to indexation completion notifications and (optionally)
sends emails when a pipeline completes for a product.
"""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.indexation_subscription import IndexationSubscription
from src.repositories.indexation_subscription_repository import (
    IndexationSubscriptionRepository,
)
from src.services.email_service import EmailServiceError, get_email_service

logger = get_logger(__name__)


class IndexationNotificationService:
    def __init__(self, repo: IndexationSubscriptionRepository) -> None:
        self._repo = repo

    async def subscribe(
        self, db: AgnosticDatabase, *, product_slug: str, email: str
    ) -> IndexationSubscription:
        sub = IndexationSubscription(product_slug=product_slug, email=email)
        return await self._repo.upsert(db, sub)

    async def notify_indexation_completed(
        self,
        db: AgnosticDatabase,
        *,
        product_slug: str,
        product_name: str,
        documents_found: int,
    ) -> int:
        """Send completion emails to all pending subscribers.

        Returns number of successfully attempted recipients. If the email service
        is not configured, returns 0 (subscriptions remain pending).
        """
        pending = await self._repo.find_pending_by_product_slug(db, product_slug)
        if not pending:
            return 0

        email_service = get_email_service()

        sent_ids: list[str] = []
        for sub in pending:
            try:
                await email_service.send_indexation_complete(
                    to_email=str(sub.email),
                    product_name=product_name,
                    product_slug=product_slug,
                    documents_found=documents_found,
                )
                sent_ids.append(sub.id)
            except EmailServiceError as exc:
                logger.warning(
                    "indexation notify email failed",
                    product_slug=product_slug,
                    email=str(sub.email),
                    error=str(exc),
                )

        if sent_ids:
            await self._repo.mark_notified(db, sent_ids)
        return len(sent_ids)
