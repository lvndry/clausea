"""Migrate topic stance labels from risk-tier names to qualitative adjectives.

Old → New:
  low_risk       → fair
  moderate_risk  → concerning
  high_risk      → harmful
  mixed          → conflicting
  not_disclosed  → not_disclosed (unchanged)

Also removes ``topic_score`` from ``overview.topic_stances`` entries.

Idempotent: re-running finds no entries matching the old stance labels and
no entries still carrying ``topic_score``, so zero documents are modified.
"""

from __future__ import annotations

import asyncio
from typing import Any

from motor.core import AgnosticDatabase

from src.core.database import db_session
from src.core.logging import get_logger
from src.migrations.base import Migration

logger = get_logger(__name__)

_STANCE_MAP = {
    "low_risk": "fair",
    "moderate_risk": "concerning",
    "high_risk": "harmful",
    "mixed": "conflicting",
}

COLLECTION = "product_intelligence"


async def migrate_topic_stances(db: AgnosticDatabase) -> dict[str, Any]:
    """Rename stance labels and strip topic_score from product_intelligence overviews."""
    col = db[COLLECTION]

    total = await col.count_documents({})
    affected = await col.count_documents({"overview.topic_stances": {"$exists": True}})

    updated = 0
    async for doc in col.find(
        {"overview.topic_stances": {"$exists": True}},
        {"_id": 1, "product_slug": 1, "overview.topic_stances": 1},
    ):
        stances = doc.get("overview", {}).get("topic_stances") or []
        new_stances = []
        changed = False
        for stance in stances:
            entry = dict(stance)
            old = entry.get("stance")
            if old in _STANCE_MAP:
                entry["stance"] = _STANCE_MAP[old]
                changed = True
            if "topic_score" in entry:
                del entry["topic_score"]
                changed = True
            new_stances.append(entry)

        if changed:
            await col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"overview.topic_stances": new_stances}},
            )
            updated += 1

    logger.info(
        "topic_stances migration complete",
        total=total,
        with_stances=affected,
        updated=updated,
    )
    return {"total": total, "with_stances": affected, "updated": updated}


class MigrateTopicStances(Migration):
    migration_id = "003_migrate_topic_stances"
    description = "Rename stance labels (low_risk→fair etc.) and strip topic_score"

    async def upgrade(self, db: AgnosticDatabase) -> dict[str, Any]:
        return await migrate_topic_stances(db)


if __name__ == "__main__":

    async def _run() -> None:
        async with db_session() as db:
            await migrate_topic_stances(db)

    asyncio.run(_run())
