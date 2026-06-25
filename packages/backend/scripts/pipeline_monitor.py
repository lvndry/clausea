"""Production pipeline monitoring — regen ticks, auto-requeue, and down alerts.

Commands:
  regen   Print PIPELINE_UPDATE every N seconds (default)
  watch   Regen loop + auto-run requeue_crawl when analysis-only drains
  down    Alert on SERVICE_DOWN_ALERT / SERVICE_RECOVERED_ALERT
  status  One-shot queue summary

Usage:
  uv run python scripts/pipeline_monitor.py --production
  uv run python scripts/pipeline_monitor.py --production --interval 300
  uv run python scripts/pipeline_monitor.py watch --production --interval 600
  uv run python scripts/pipeline_monitor.py down --production --interval 60
  uv run python scripts/pipeline_monitor.py status --production
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

HEALTHY_RAILWAY = frozenset({"success", "active", "deployed", "online"})
STALL_MINUTES = 3
STALL_PENDING_MIN = 5


def _run_requeue_crawl(*, use_production: bool) -> str:
    cmd = [sys.executable, "scripts/requeue_crawl.py"]
    if use_production:
        cmd.append("--production")
    proc = subprocess.run(
        cmd,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    return tail[-1] if tail else f"exit={proc.returncode}"


def _railway_crawler_status() -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["railway", "service", "status", "--service", "crawler"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"railway_cli_error: {exc}"
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "railway status failed").strip()
    status = deployment = None
    for line in proc.stdout.splitlines():
        if line.startswith("Status:"):
            status = line.split(":", 1)[1].strip()
        elif line.startswith("Deployment:"):
            deployment = line.split(":", 1)[1].strip()
    return status, deployment


def _down_reason(
    railway_status: str | None, active_workers: int, pending: int, last_active
) -> str | None:
    if railway_status is None:
        return "Could not reach Railway CLI for crawler status"
    if railway_status.lower() not in HEALTHY_RAILWAY:
        return f"Railway crawler deploy status is {railway_status}"
    if pending >= STALL_PENDING_MIN and active_workers == 0 and last_active is None:
        return (
            f"Crawler deploy is {railway_status} but no worker activity for "
            f"{STALL_MINUTES}+ minutes ({pending} jobs pending)"
        )
    return None


async def _tick_regen(db, *, worker_slots: int) -> str:
    from src.services.pipeline_snapshot import (
        format_pipeline_update,
        in_progress_labels,
        overview_counts,
        queue_counts,
        regen_batch_stats,
    )

    regen = await regen_batch_stats(db)
    counts = await queue_counts(db)
    overviews, products = await overview_counts(db)
    labels = await in_progress_labels(db)
    ts = datetime.now(UTC).strftime("%H:%M UTC")
    return format_pipeline_update(
        ts=ts,
        regen=regen,
        counts=counts,
        overviews=overviews,
        products=products,
        labels=labels,
        worker_slots=worker_slots,
    )


async def _cmd_regen(*, interval: int, use_production: bool, worker_slots: int) -> None:
    from src.ops.script_env import open_db, resolve_production

    resolve_production(use_production=use_production)
    client, db = open_db(prefer_production=use_production)
    label = "PRODUCTION" if use_production else "local"
    print(f"Monitor [{label}] regen: {interval}s — PIPELINE_UPDATE lines", flush=True)
    try:
        while True:
            try:
                print(await _tick_regen(db, worker_slots=worker_slots), flush=True)
            except Exception as exc:
                print(f"PIPELINE_UPDATE ERROR: {exc}", flush=True)
            await asyncio.sleep(interval)
    finally:
        client.close()


async def _cmd_watch(*, interval: int, use_production: bool, worker_slots: int) -> None:
    from src.ops.script_env import open_db, resolve_production
    from src.services.pipeline_snapshot import queue_counts

    resolve_production(use_production=use_production)
    client, db = open_db(prefer_production=use_production)
    requeue_done = False
    label = "PRODUCTION" if use_production else "local"
    print(f"Monitor [{label}] watch: {interval}s — regen + auto requeue_crawl", flush=True)
    try:
        while True:
            try:
                print(await _tick_regen(db, worker_slots=worker_slots), flush=True)
                counts = await queue_counts(db)
                if counts["pending_skip"] + counts["active_skip"] == 0 and not requeue_done:
                    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                    print(f"[{ts}] ACTION: analysis-only drained — requeue_crawl.py", flush=True)
                    print(
                        f"[{ts}] requeue_crawl: {_run_requeue_crawl(use_production=use_production)}",
                        flush=True,
                    )
                    requeue_done = True
            except Exception as exc:
                print(f"PIPELINE_UPDATE ERROR: {exc}", flush=True)
            await asyncio.sleep(interval)
    finally:
        client.close()


async def _cmd_down(*, interval: int) -> None:
    from src.ops.script_env import open_db, resolve_production
    from src.services.pipeline_snapshot import IN_PROGRESS

    resolve_production(use_production=True, require=True)
    client, db = open_db(prefer_production=True)
    was_down = False
    print(f"Monitor [PRODUCTION] down-alert: {interval}s", flush=True)
    try:
        while True:
            ts = datetime.now(UTC).strftime("%H:%M:%S UTC")
            try:
                railway_status, deployment = _railway_crawler_status()
                active = await db.pipeline_jobs.count_documents(
                    {"active": True, "status": {"$in": list(IN_PROGRESS)}}
                )
                pending = await db.pipeline_jobs.count_documents(
                    {"active": True, "status": "pending"}
                )
                cutoff = datetime.now(UTC) - timedelta(minutes=STALL_MINUTES)
                recent = await db.pipeline_jobs.find_one(
                    {"status": {"$in": list(IN_PROGRESS)}, "updated_at": {"$gte": cutoff}},
                    sort=[("updated_at", -1)],
                    projection={"updated_at": 1},
                )
                reason = _down_reason(
                    railway_status,
                    active,
                    pending,
                    recent.get("updated_at") if recent else None,
                )
                if reason:
                    tag = "SERVICE_STILL_DOWN" if was_down else "SERVICE_DOWN_ALERT"
                    print(
                        f"{tag} [{ts}] {reason} | workers={active}/8 pending={pending} "
                        f"deploy={deployment or 'unknown'}",
                        flush=True,
                    )
                    was_down = True
                elif was_down:
                    print(
                        f"SERVICE_RECOVERED_ALERT [{ts}] railway={railway_status} "
                        f"workers={active}/8 pending={pending}",
                        flush=True,
                    )
                    was_down = False
                else:
                    print(
                        f"SERVICE_OK [{ts}] railway={railway_status} "
                        f"workers={active}/8 pending={pending}",
                        flush=True,
                    )
            except Exception as exc:
                print(f"SERVICE_DOWN_ALERT [{ts}] {exc}", flush=True)
            await asyncio.sleep(interval)
    finally:
        client.close()


async def _cmd_status(*, use_production: bool) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Production pipeline monitor")
    parser.add_argument("--production", action="store_true", help="Use PRODUCTION_MONGO_URI")
    parser.add_argument(
        "--interval", type=int, default=None, help="Poll interval seconds (regen/watch/down)"
    )
    parser.add_argument(
        "--worker-slots",
        type=int,
        default=int(os.getenv("CRAWLER_EXPECTED_CONCURRENCY", "8")),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="regen",
        choices=("regen", "watch", "down", "status"),
        help="Monitor mode (default: regen)",
    )
    args = parser.parse_args()

    if args.command == "regen":
        asyncio.run(
            _cmd_regen(
                interval=args.interval or 300,
                use_production=args.production,
                worker_slots=args.worker_slots,
            )
        )
    elif args.command == "watch":
        asyncio.run(
            _cmd_watch(
                interval=args.interval or 600,
                use_production=args.production,
                worker_slots=args.worker_slots,
            )
        )
    elif args.command == "down":
        asyncio.run(_cmd_down(interval=args.interval or 60))
    else:
        asyncio.run(_cmd_status(use_production=args.production))


if __name__ == "__main__":
    main()
