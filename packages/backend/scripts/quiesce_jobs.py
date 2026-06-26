"""Mark pipeline jobs non-retryable so worker sweeps stop refilling the queue.

Sets active/in-flight/interrupted jobs to failed with auto_retry_disabled, and
disables auto-retry on all other failed jobs the worker would otherwise revive.

Usage:
    uv run python scripts/quiesce_jobs.py --production --dry-run
    uv run python scripts/quiesce_jobs.py --production
    uv run python scripts/quiesce_jobs.py --production --keep-slugs stripe
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from dotenv import load_dotenv

load_dotenv()

IN_FLIGHT = ("pending", "crawling", "synthesising", "generating_overview", "interrupted")
REASON = "manual_ops_quiesce"


async def main(*, dry_run: bool, use_production: bool, keep_slugs: set[str]) -> None:
    from src.ops.script_env import open_db, resolve_production

    resolve_production(use_production=use_production)
    if use_production:
        print("Using PRODUCTION_MONGO_URI")

    client, db = open_db(prefer_production=use_production)
    try:
        now = datetime.now(UTC).replace(tzinfo=None)

        in_flight_query = {
            "$or": [
                {"active": True},
                {"status": {"$in": list(IN_FLIGHT)}},
            ]
        }
        if keep_slugs:
            in_flight_query = {
                "$and": [
                    in_flight_query,
                    {"product_slug": {"$nin": sorted(keep_slugs)}},
                ]
            }

        in_flight = await db.pipeline_jobs.count_documents(in_flight_query)
        retryable_failed = await db.pipeline_jobs.count_documents(
            {"status": "failed", "auto_retry_disabled": {"$ne": True}}
        )
        interrupted = await db.pipeline_jobs.count_documents({"status": "interrupted"})
        print(
            f"Would quiesce in_flight={in_flight} retryable_failed={retryable_failed} "
            f"interrupted={interrupted} keep={sorted(keep_slugs) or 'none'}"
        )

        if dry_run:
            sample = (
                await db.pipeline_jobs.find(
                    in_flight_query, {"product_slug": 1, "status": 1, "active": 1}
                )
                .limit(15)
                .to_list(15)
            )
            for j in sample:
                print(
                    f"  [dry-run] {j['product_slug']} status={j['status']} active={j.get('active')}"
                )
            return

        r1 = await db.pipeline_jobs.update_many(
            in_flight_query,
            {
                "$set": {
                    "status": "failed",
                    "active": False,
                    "error": "interrupted",
                    "error_detail": "Quiesced by ops — do not auto-retry",
                    "auto_retry_disabled": True,
                    "auto_retry_disabled_reason": REASON,
                    "updated_at": now,
                    "completed_at": now,
                }
            },
        )
        r2 = await db.pipeline_jobs.update_many(
            {"status": "failed", "auto_retry_disabled": {"$ne": True}},
            {
                "$set": {
                    "auto_retry_disabled": True,
                    "auto_retry_disabled_reason": REASON,
                    "updated_at": now,
                }
            },
        )
        active_left = await db.pipeline_jobs.count_documents({"active": True})
        interrupted_left = await db.pipeline_jobs.count_documents({"status": "interrupted"})
        retryable_left = await db.pipeline_jobs.count_documents(
            {"status": "failed", "auto_retry_disabled": {"$ne": True}}
        )
        print(
            f"Done: quiesced_in_flight={r1.modified_count} "
            f"disabled_failed_retry={r2.modified_count} "
            f"active_left={active_left} interrupted_left={interrupted_left} "
            f"retryable_failed_left={retryable_left}"
        )
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quiesce pipeline jobs (no worker auto-retry)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument(
        "--keep-slugs",
        nargs="*",
        default=[],
        help="Do not quiesce active/in-flight jobs for these slugs",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            dry_run=args.dry_run,
            use_production=args.production,
            keep_slugs=set(args.keep_slugs),
        )
    )
