"""Watch production pipeline progress and requeue full crawls when analysis-only drains.

Usage:
  PRODUCTION_MONGO_URI=... uv run python scripts/pipeline_watch.py
  uv run python scripts/pipeline_watch.py --production --interval 600
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

IN_PROGRESS = ("crawling", "synthesising", "generating_overview")


def _resolve_production(use_production: bool) -> str:
    if use_production:
        prod_uri = os.getenv("PRODUCTION_MONGO_URI")
        if not prod_uri:
            print("ERROR: PRODUCTION_MONGO_URI not set", flush=True)
            sys.exit(1)
        os.environ["MONGO_URI"] = prod_uri
        return prod_uri
    uri = os.getenv("MONGO_URI")
    if not uri:
        print("ERROR: MONGO_URI not set", flush=True)
        sys.exit(1)
    return uri


async def _snapshot(uri: str, db_name: str) -> dict[str, int]:
    client = AsyncIOMotorClient(uri)
    try:
        db = client[db_name]
        pending_skip = await db.pipeline_jobs.count_documents(
            {"status": "pending", "active": True, "skip_crawl": True}
        )
        pending_full = await db.pipeline_jobs.count_documents(
            {"status": "pending", "active": True, "skip_crawl": {"$ne": True}}
        )
        active_skip = await db.pipeline_jobs.count_documents(
            {"status": {"$in": list(IN_PROGRESS)}, "skip_crawl": True}
        )
        active_full = await db.pipeline_jobs.count_documents(
            {"status": {"$in": list(IN_PROGRESS)}, "skip_crawl": {"$ne": True}}
        )
        completed_skip = await db.pipeline_jobs.count_documents(
            {"status": "completed", "skip_crawl": True}
        )
        completed_total = await db.pipeline_jobs.count_documents({"status": "completed"})
        running = active_skip + active_full
        return {
            "pending_skip": pending_skip,
            "pending_full": pending_full,
            "active_skip": active_skip,
            "active_full": active_full,
            "completed_skip": completed_skip,
            "completed_total": completed_total,
            "running": running,
        }
    finally:
        client.close()


def _run_requeue_crawl(use_production: bool, *, missing_overviews_only: bool) -> str:
    cmd = [sys.executable, "scripts/requeue_crawl.py"]
    if use_production:
        cmd.append("--production")
    if missing_overviews_only:
        cmd.append("--missing-overviews")
    env = os.environ.copy()
    proc = subprocess.run(
        cmd,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    summary = tail[-1] if tail else f"exit={proc.returncode}"
    return summary


async def _tick(
    use_production: bool, *, requeue_crawl_done: bool, missing_overviews_only: bool
) -> bool:
    uri = _resolve_production(use_production)
    db_name = os.getenv("MONGODB_DATABASE", "clausea")
    stats = await _snapshot(uri, db_name)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    analysis_backlog = stats["pending_skip"] + stats["active_skip"]
    print(
        f"[{ts}] analysis-only: pending={stats['pending_skip']} active={stats['active_skip']} "
        f"completed={stats['completed_skip']} | full-crawl: pending={stats['pending_full']} "
        f"active={stats['active_full']} | workers={stats['running']}/8 "
        f"completed_total={stats['completed_total']}",
        flush=True,
    )

    if analysis_backlog == 0 and not requeue_crawl_done:
        print(
            f"[{ts}] ACTION: analysis-only backlog drained — running requeue_crawl.py", flush=True
        )
        summary = _run_requeue_crawl(use_production, missing_overviews_only=missing_overviews_only)
        print(f"[{ts}] requeue_crawl: {summary}", flush=True)
        return True

    return requeue_crawl_done


async def main(*, use_production: bool, interval: int, missing_overviews_only: bool) -> None:
    if use_production:
        print("Watching PRODUCTION pipeline (10-min updates)", flush=True)
    requeue_done = False
    while True:
        try:
            requeue_done = await _tick(
                use_production,
                requeue_crawl_done=requeue_done,
                missing_overviews_only=missing_overviews_only,
            )
        except Exception as exc:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"[{ts}] ERROR: {exc}", flush=True)
        await asyncio.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline watch with auto requeue_crawl")
    parser.add_argument("--production", action="store_true")
    parser.add_argument(
        "--interval", type=int, default=600, help="Seconds between updates (default 600)"
    )
    parser.add_argument(
        "--missing-overviews-only",
        action="store_true",
        help="After analysis-only drains, requeue crawl only for products without overviews",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            use_production=args.production,
            interval=args.interval,
            missing_overviews_only=args.missing_overviews_only,
        )
    )
