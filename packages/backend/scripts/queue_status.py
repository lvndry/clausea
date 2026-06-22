"""Read-only snapshot of the pipeline_jobs queue. Usage: uv run python scripts/queue_status.py

Aggregates job counts by status and lists currently-crawling products and recent
failures. Connects to PRODUCTION_MONGO_URI when set, else MONGO_URI. Never writes.
"""

import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient


async def main() -> None:
    uri = os.getenv("PRODUCTION_MONGO_URI") or os.getenv("MONGO_URI")
    if not uri:
        raise SystemExit("No PRODUCTION_MONGO_URI or MONGO_URI set")
    db_name = os.getenv("MONGODB_DATABASE", "clausea")
    client = AsyncIOMotorClient(uri)
    db = client[db_name]

    by_status: dict[str, int] = {}
    async for row in db.pipeline_jobs.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[row["_id"]] = row["n"]

    overviews = await db.product_overviews.count_documents({})
    total = sum(by_status.values())

    order = [
        "pending",
        "crawling",
        "summarizing",
        "generating_overview",
        "completed",
        "no_documents",
        "failed",
    ]
    parts = [f"{s}={by_status.get(s, 0)}" for s in order if s in by_status]
    extra = [f"{s}={n}" for s, n in by_status.items() if s not in order]
    print(f"jobs={total} " + " ".join(parts + extra) + f" overviews={overviews}")

    crawling = await db.pipeline_jobs.find(
        {"status": {"$in": ["crawling", "summarizing", "generating_overview"]}}
    ).to_list(length=20)
    if crawling:
        active = [
            f"{j['product_slug']}({j['status']},att={j.get('attempts', 0)})" for j in crawling
        ]
        print("in-progress: " + ", ".join(active))

    failed = await db.pipeline_jobs.find({"status": "failed"}).sort("updated_at", -1).to_list(20)
    if failed:
        print(f"failed (top {min(len(failed), 20)} by recency):")
        for j in failed:
            print(f"  {j['product_slug']:24} att={j.get('attempts', 0)} err={j.get('error')}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
