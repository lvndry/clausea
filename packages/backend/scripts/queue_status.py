"""Read-only snapshot of the pipeline_jobs queue.

Usage:
    uv run python scripts/queue_status.py
    uv run python scripts/queue_status.py --production
"""

from __future__ import annotations

import argparse
import asyncio

from dotenv import load_dotenv

load_dotenv()


async def main(*, use_production: bool) -> None:
    from src.ops.script_env import open_db, resolve_production
    from src.services.pipeline_snapshot import full_queue_snapshot

    resolve_production(use_production=use_production)
    client, db = open_db(prefer_production=use_production)
    try:
        snap = await full_queue_snapshot(db)
        by_status = snap["by_status"]
        order = [
            "pending",
            "crawling",
            "synthesising",
            "generating_overview",
            "completed",
            "no_documents",
            "failed",
        ]
        parts = [f"{s}={by_status.get(s, 0)}" for s in order if s in by_status]
        extra = [f"{s}={n}" for s, n in by_status.items() if s not in order]
        print(
            f"jobs={snap['total']} " + " ".join(parts + extra) + f" overviews={snap['overviews']}"
        )
        if snap["in_progress"]:
            print(
                "in-progress: "
                + ", ".join(
                    f"{j['product_slug']}({j['status']},att={j.get('attempts', 0)})"
                    for j in snap["in_progress"]
                )
            )
        if snap["failed"]:
            print(f"failed (top {min(len(snap['failed']), 20)} by recency):")
            for j in snap["failed"]:
                print(f"  {j['product_slug']:24} att={j.get('attempts', 0)} err={j.get('error')}")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline queue snapshot (read-only)")
    parser.add_argument("--production", action="store_true", help="Use PRODUCTION_MONGO_URI")
    args = parser.parse_args()
    asyncio.run(main(use_production=args.production))
