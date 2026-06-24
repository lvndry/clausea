"""Migrate topic stance labels from risk-tier names to qualitative adjectives.

Old → New:
  low_risk       → fair
  moderate_risk  → concerning
  high_risk      → harmful
  mixed          → conflicting
  not_disclosed  → not_disclosed (unchanged)

Also removes topic_score from overview.topic_stances entries.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent.parent / ".env")

MONGO_URI = os.environ["PRODUCTION_MONGO_URI"]

_STANCE_MAP = {
    "low_risk": "fair",
    "moderate_risk": "concerning",
    "high_risk": "harmful",
    "mixed": "conflicting",
}

COLLECTION = "product_intelligence"


async def run(*, dry_run: bool = False) -> None:
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
    try:
        default_db = client.get_default_database()
        db_name = default_db.name if default_db is not None else "clausea"
    except Exception:
        db_name = "clausea"
    db = client[db_name]
    col = db[COLLECTION]

    total = await col.count_documents({})
    print(f"Collection '{COLLECTION}': {total} documents")

    affected = await col.count_documents({"overview.topic_stances": {"$exists": True}})
    print(f"Documents with overview.topic_stances: {affected}")

    if dry_run:
        print("Dry run — no changes written.")
        client.close()
        return

    updated = 0
    async for doc in col.find(
        {"overview.topic_stances": {"$exists": True}},
        {"_id": 1, "product_slug": 1, "overview.topic_stances": 1},
    ):
        stances = doc.get("overview", {}).get("topic_stances") or []
        new_stances = []
        changed = False
        for s in stances:
            entry = dict(s)
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

    print(f"Updated {updated} documents.")
    client.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(run(dry_run=dry_run))
