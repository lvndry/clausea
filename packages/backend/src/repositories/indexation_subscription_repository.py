"""Indexation subscription repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.indexation_subscription import IndexationSubscription
from src.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


class IndexationSubscriptionRepository(BaseRepository):
    COLLECTION = "indexation_subscriptions"

    async def upsert(
        self, db: AgnosticDatabase, sub: IndexationSubscription
    ) -> IndexationSubscription:
        """Upsert subscription by (product_slug, email)."""
        await db[self.COLLECTION].update_one(
            {"product_slug": sub.product_slug, "email": str(sub.email)},
            {"$setOnInsert": sub.model_dump()},
            upsert=True,
        )
        return sub

    async def find_pending_by_product_slug(
        self, db: AgnosticDatabase, product_slug: str
    ) -> list[IndexationSubscription]:
        cursor = (
            db[self.COLLECTION]
            .find({"product_slug": product_slug, "notified_at": None})
            .sort("created_at", 1)
        )
        items: list[dict[str, Any]] = await cursor.to_list(length=500)
        return [IndexationSubscription(**i) for i in items]

    async def mark_notified(self, db: AgnosticDatabase, ids: list[str]) -> None:
        if not ids:
            return
        await db[self.COLLECTION].update_many(
            {"id": {"$in": ids}},
            {"$set": {"notified_at": datetime.now()}},
        )
