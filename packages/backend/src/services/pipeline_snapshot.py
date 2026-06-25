"""Read-only pipeline queue snapshots for ops scripts and monitors."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

IN_PROGRESS = ("crawling", "synthesising", "generating_overview")
DEFAULT_WORKER_SLOTS = 8


async def queue_counts(db: AsyncIOMotorDatabase) -> dict[str, int]:
    pending_skip = await db.pipeline_jobs.count_documents(
        {"active": True, "status": "pending", "skip_crawl": True}
    )
    active_skip = await db.pipeline_jobs.count_documents(
        {"active": True, "status": {"$in": list(IN_PROGRESS)}, "skip_crawl": True}
    )
    pending_full = await db.pipeline_jobs.count_documents(
        {"active": True, "status": "pending", "skip_crawl": {"$ne": True}}
    )
    active_full = await db.pipeline_jobs.count_documents(
        {"active": True, "status": {"$in": list(IN_PROGRESS)}, "skip_crawl": {"$ne": True}}
    )
    return {
        "pending_skip": pending_skip,
        "active_skip": active_skip,
        "pending_full": pending_full,
        "active_full": active_full,
        "workers": active_skip + active_full,
    }


async def overview_counts(db: AsyncIOMotorDatabase) -> tuple[int, int]:
    overviews = await db.product_intelligence.count_documents(
        {"overview": {"$exists": True, "$ne": None}}
    )
    products = await db.products.count_documents({})
    return overviews, products


async def regen_batch_stats(
    db: AsyncIOMotorDatabase,
    *,
    since_hour_utc: int = 8,
) -> Counter:
    since = datetime.now(UTC).replace(hour=since_hour_utc, minute=0, second=0, microsecond=0)
    batch = await db.pipeline_jobs.find(
        {"skip_crawl": True, "created_at": {"$gte": since}}
    ).to_list(500)
    return Counter(j.get("status") for j in batch)


async def in_progress_labels(db: AsyncIOMotorDatabase, *, limit: int = 8) -> str:
    jobs = (
        await db.pipeline_jobs.find({"active": True, "status": {"$in": list(IN_PROGRESS)}})
        .sort("updated_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    if not jobs:
        return "none"
    return ", ".join(f"{j['product_slug']}({j['status'][:5]})" for j in jobs)


def format_pipeline_update(
    *,
    ts: str,
    regen: Counter,
    counts: dict[str, int],
    overviews: int,
    products: int,
    labels: str,
    worker_slots: int = DEFAULT_WORKER_SLOTS,
) -> str:
    regen_active = sum(regen.get(s, 0) for s in IN_PROGRESS)
    regen_fail = regen.get("analysis_failed", 0) + regen.get("failed", 0)
    return (
        f"PIPELINE_UPDATE [{ts}] regen_ok={regen.get('completed', 0)} regen_fail={regen_fail} "
        f"regen_pending={regen.get('pending', 0)} regen_active={regen_active} | "
        f"analysis_q={counts['pending_skip']} crawl_q={counts['pending_full']} "
        f"workers={counts['workers']}/{worker_slots} | overviews={overviews}/{products} | {labels}"
    )


async def full_queue_snapshot(db: AsyncIOMotorDatabase) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    async for row in db.pipeline_jobs.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[row["_id"]] = row["n"]
    overviews, _ = await overview_counts(db)
    crawling = (
        await db.pipeline_jobs.find({"status": {"$in": list(IN_PROGRESS)}})
        .sort("updated_at", -1)
        .limit(20)
        .to_list(20)
    )
    failed = (
        await db.pipeline_jobs.find({"status": "failed"})
        .sort("updated_at", -1)
        .limit(20)
        .to_list(20)
    )
    return {
        "by_status": by_status,
        "total": sum(by_status.values()),
        "overviews": overviews,
        "in_progress": crawling,
        "failed": failed,
    }
