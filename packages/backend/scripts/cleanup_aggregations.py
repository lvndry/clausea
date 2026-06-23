"""One-time cleanup: remove orphan aggregations and slim stored evidence.

Aggregations duplicate evidence already stored on findings. The topics API only
needs up to TOPIC_CITATION_LIMIT spans per finding, but legacy rows kept every
merged span (~800 KB each).

Operations (idempotent):
1. Delete aggregations for products whose pipeline job is not ``completed``.
2. Cap ``findings[].evidence`` and ``conflicts[].evidence`` to TOPIC_CITATION_LIMIT.

Usage:
    uv run python scripts/cleanup_aggregations.py
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()


async def run_cleanup() -> None:
    import certifi
    from motor.motor_asyncio import AsyncIOMotorClient

    from src.core.config import config
    from src.models.finding import Aggregation
    from src.repositories.aggregation_repository import AggregationRepository
    from src.repositories.document_repository import DocumentRepository
    from src.repositories.finding_repository import FindingRepository
    from src.services.aggregation_service import AggregationService

    uri = config.database.mongodb_uri
    if not uri:
        print("MONGO_URI is not set.", file=sys.stderr)
        sys.exit(1)

    if "+srv" in uri:
        client = AsyncIOMotorClient(uri, tls=True, tlsCAFile=certifi.where())
    else:
        client = AsyncIOMotorClient(uri)

    db = client[config.database.mongodb_database]

    stats_before = await db.command("collStats", "aggregations")
    count_before = stats_before.get("count", 0)
    size_before_mb = stats_before.get("size", 0) / 1024 / 1024

    completed_ids: set[str] = set()
    async for job in db.pipeline_jobs.find({"status": "completed"}, {"product_id": 1}):
        pid = job.get("product_id")
        if pid:
            completed_ids.add(pid)

    orphan_result = await db.aggregations.delete_many({"product_id": {"$nin": list(completed_ids)}})
    print(f"Deleted {orphan_result.deleted_count} orphan aggregation(s)")

    service = AggregationService(
        DocumentRepository(),
        FindingRepository(),
        AggregationRepository(),
    )

    slimmed = 0
    async for raw in db.aggregations.find({}):
        aggregation = Aggregation(**raw)
        slim = service._slim_aggregation_for_storage(aggregation)
        if slim.model_dump() != aggregation.model_dump():
            await db.aggregations.replace_one(
                {"product_id": aggregation.product_id}, slim.model_dump()
            )
            slimmed += 1

    stats_after = await db.command("collStats", "aggregations")
    count_after = stats_after.get("count", 0)
    size_after_mb = stats_after.get("size", 0) / 1024 / 1024
    storage_after_mb = stats_after.get("storageSize", 0) / 1024 / 1024

    print(
        f"Aggregations: {count_before} -> {count_after} docs, "
        f"data {size_before_mb:.1f} MB -> {size_after_mb:.1f} MB, "
        f"storage {storage_after_mb:.1f} MB"
    )
    print(f"Slimmed evidence on {slimmed} aggregation(s)")
    client.close()


if __name__ == "__main__":
    asyncio.run(run_cleanup())
