"""Backfill: mark orphan overview citations as stale in product_intelligence.

Production data contains citations whose ``document_id`` no longer exists in the
``documents`` collection — the source document was deleted or superseded on
re-crawl, but the citations referencing it were never invalidated. This script
scans every ``product_intelligence`` overview, finds citations whose
``document_id`` is missing from ``documents``, and flags them ``stale: True``
so the UI filter can hide them.

Idempotent: re-running re-scans orphans and re-marks them stale (a no-op on
already-stale citations).
"""

from __future__ import annotations

import asyncio
from typing import Any

from motor.core import AgnosticDatabase

from src.core.database import db_session
from src.core.logging import get_logger
from src.migrations.base import Migration
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository

logger = get_logger(__name__)


async def backfill_orphan_citations(db: AgnosticDatabase) -> dict[str, Any]:
    """Mark stale every overview citation pointing at a deleted document.

    Returns a detail dict with the reference counts and the total number of
    citations flagged stale.
    """
    repo = ProductIntelligenceRepository()
    total_marked = 0

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
        return {"referenced": 0, "existing": 0, "orphan": 0, "marked_stale": 0}

    existing_ids: set[str] = set()
    async for row in db.documents.find({"id": {"$in": list(referenced_ids)}}, {"_id": 0, "id": 1}):
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
    return {
        "referenced": len(referenced_ids),
        "existing": len(existing_ids),
        "orphan": len(orphan_ids),
        "marked_stale": total_marked,
    }


class BackfillOrphanCitations(Migration):
    migration_id = "002_backfill_orphan_citations"
    description = "Flag overview citations pointing at deleted documents as stale"

    async def upgrade(self, db: AgnosticDatabase) -> dict[str, Any]:
        return await backfill_orphan_citations(db)


if __name__ == "__main__":

    async def _run() -> None:
        async with db_session() as db:
            await backfill_orphan_citations(db)

    asyncio.run(_run())
