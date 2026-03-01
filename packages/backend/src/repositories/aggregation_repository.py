"""Aggregation repository for data access operations."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.finding import Aggregation
from src.repositories.base_repository import BaseRepository


class AggregationRepository(BaseRepository):
    """Repository for product-level aggregations."""

    async def save(self, db: AgnosticDatabase, aggregation: Aggregation) -> None:
        data = aggregation.model_dump()
        await db.aggregations.update_one(
            {"product_id": aggregation.product_id}, {"$set": data}, upsert=True
        )

    async def get(self, db: AgnosticDatabase, product_id: str) -> Aggregation | None:
        data = await db.aggregations.find_one({"product_id": product_id})
        return Aggregation(**data) if data else None
