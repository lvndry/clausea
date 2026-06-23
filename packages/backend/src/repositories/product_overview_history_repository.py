from __future__ import annotations

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.product_intelligence import OverviewSnapshot
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository

logger = get_logger(__name__)


class ProductOverviewHistoryRepository:
    """Reads overview history from embedded product_intelligence snapshots."""

    async def find_by_product(
        self, db: AgnosticDatabase, product_slug: str, limit: int = 50
    ) -> list[OverviewSnapshot]:
        intelligence = await ProductIntelligenceRepository().get_by_slug(db, product_slug)
        if not intelligence:
            return []
        return intelligence.overview_history[:limit]

    async def save_snapshot(self, *args, **kwargs) -> None:
        # History is recorded by ProductIntelligenceService.save_overview.
        logger.debug("save_snapshot is handled by ProductIntelligenceService.save_overview")
