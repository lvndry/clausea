"""Legacy aggregation repository — reads old collection for migration scripts only."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.finding import Aggregation
from src.repositories.base_repository import BaseRepository


class AggregationRepository(BaseRepository):
    async def save(self, db: AgnosticDatabase, aggregation: Aggregation) -> None:
        raise NotImplementedError("aggregations collection is deprecated; use product_intelligence")

    async def get(self, db: AgnosticDatabase, product_id: str) -> Aggregation | None:
        row = await db.aggregations.find_one({"product_id": product_id})
        return Aggregation(**row) if row else None
