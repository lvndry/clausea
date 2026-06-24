"""Backfill: mark orphan overview citations as stale in product_intelligence.

Production data contains citations whose ``document_id`` no longer exists in the
``documents`` collection — the source document was deleted or superseded on
re-crawl, but the citations referencing it were never invalidated. This script
scans every ``product_intelligence`` overview, finds citations whose
``document_id`` is missing from ``documents``, and flags them ``stale: True``
so the UI filter can hide them.

Run with:  uv run python -m src.migrations.backfill_orphan_citations
"""

from __future__ import annotations

import asyncio

from src.core.database import db_session
from src.core.logging import get_logger
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository

logger = get_logger(__name__)


async def backfill_orphan_citations() -> int:
    """Mark stale every overview citation pointing at a deleted document.

    Returns the total number of citations flagged stale.
    """
    repo = ProductIntelligenceRepository()
    total_marked = 0

    async with db_session() as db:
        cursor = db[repo.COLLECTION].find(
            {"overview": {"$exists": True, "$ne": None}},
            {"_id": 0, "overview.topic_stances.supporting_citations.document_id": 1},
        )

        referenced_ids: set[str] = set()
        async for row in cursor:
            for stance in (row.get("overview") or {}).get("topic_stances") or []:
                for cite in stance.get("supporting_citations") or []:
                    document_id = cite.get("document_id")
                    if isinstance(document_id, str) and document_id:
                        referenced_ids.add(document_id)

        if not referenced_ids:
            logger.info("No citations found across product_intelligence overviews.")
            return 0

        existing_ids: set[str] = set()
        async for row in db.documents.find(
            {"id": {"$in": list(referenced_ids)}}, {"_id": 0, "id": 1}
        ):
            if row.get("id"):
                existing_ids.add(row["id"])

        orphan_ids = referenced_ids - existing_ids
        logger.info(
            "Referenced document_ids: %d | existing: %d | orphan: %d",
            len(referenced_ids),
            len(existing_ids),
            len(orphan_ids),
        )

        for orphan_id in sorted(orphan_ids):
            marked = await repo.mark_citations_stale_for_document(db, orphan_id)
            if marked:
                logger.info(
                    "Marked %d citation(s) stale for orphan document_id=%s",
                    marked,
                    orphan_id,
                )
                total_marked += marked

        logger.info("Backfill complete. Total citations marked stale: %d", total_marked)
        return total_marked


if __name__ == "__main__":
    asyncio.run(backfill_orphan_citations())
