"""One-shot production maintenance after product_intelligence refactor.

1. Drop legacy MongoDB collections (data already in product_intelligence).
2. Unstick the pipeline queue (defer poison jobs, reset quarantined failures).
3. Backfill product_intelligence for products that missed the migration.

Usage:
    uv run python scripts/post_refactor_maintenance.py --use-production
    uv run python scripts/post_refactor_maintenance.py --use-production --skip-backfill
    uv run python scripts/post_refactor_maintenance.py --use-production --only-backfill
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from datetime import UTC, datetime

from dotenv import load_dotenv

load_dotenv()

LEGACY_COLLECTIONS = (
    "findings",
    "aggregations",
    "product_overviews",
    "document_versions",
    "product_overview_history",
    "product_compliance",
    "product_explainers",
    "deep_analyses",
)

FRESH_STEPS = [
    {
        "name": name,
        "status": "pending",
        "message": None,
        "progress_current": None,
        "progress_total": None,
        "progress_percent": None,
        "started_at": None,
        "completed_at": None,
    }
    for name in ("crawling", "synthesising", "generating_overview")
]

HIGH_ATTEMPT_DEFER_THRESHOLD = 10
NON_RETRYABLE_ERRORS = frozenset(
    {
        "product_not_found",
        "crawl_robots_blocked",
        "no_documents_found",
        "domain_circuit_breaker",
    }
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post-refactor production maintenance")
    parser.add_argument(
        "--use-production",
        action="store_true",
        help="Use PRODUCTION_MONGO_URI instead of MONGO_URI",
    )
    parser.add_argument(
        "--skip-backfill",
        action="store_true",
        help="Only drop legacy collections and reset pipeline",
    )
    parser.add_argument(
        "--only-backfill",
        action="store_true",
        help="Only run intelligence backfill (skip drop + pipeline reset)",
    )
    parser.add_argument(
        "--skip-overview",
        action="store_true",
        help="Backfill rollups only; skip LLM overview generation",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="SLUG",
        help="Skip these product slugs during backfill (repeatable)",
    )
    parser.add_argument(
        "slugs",
        nargs="*",
        help="Optional explicit slugs to backfill (default: auto-detect missing intelligence)",
    )
    return parser.parse_args()


async def _drop_legacy_collections(db) -> list[str]:
    dropped: list[str] = []
    existing = set(await db.list_collection_names())
    for name in LEGACY_COLLECTIONS:
        if name not in existing:
            print(f"[drop] skip {name} (not present)")
            continue
        count = await db[name].count_documents({})
        await db[name].drop()
        dropped.append(f"{name} ({count} docs)")
        print(f"[drop] {name}: removed {count} documents")
    return dropped


async def _unstick_pipeline(db) -> dict[str, int]:
    now = datetime.now()
    stats: dict[str, int] = {}

    in_progress = ["crawling", "synthesising", "generating_overview"]
    high_attempt = await db.pipeline_jobs.find(
        {"status": {"$in": in_progress}, "attempts": {"$gte": HIGH_ATTEMPT_DEFER_THRESHOLD}},
        {"product_slug": 1, "attempts": 1},
    ).to_list(length=100)
    if high_attempt:
        slugs = [j["product_slug"] for j in high_attempt]
        result = await db.pipeline_jobs.update_many(
            {"product_slug": {"$in": slugs}, "status": {"$in": in_progress}},
            {
                "$set": {
                    "status": "failed",
                    "active": False,
                    "error": "deferred",
                    "error_detail": (
                        f"Deferred during maintenance: {HIGH_ATTEMPT_DEFER_THRESHOLD}+ attempts "
                        "without completion. Re-trigger manually when ready."
                    ),
                    "auto_retry_disabled": True,
                    "auto_retry_disabled_reason": "maintenance: high-attempt defer",
                    "completed_at": now,
                    "updated_at": now,
                }
            },
        )
        stats["deferred_high_attempt"] = result.modified_count
        print(
            f"[pipeline] deferred {result.modified_count} high-attempt in-progress job(s): {slugs}"
        )

    reset_in_progress = await db.pipeline_jobs.update_many(
        {"status": {"$in": in_progress}, "active": True},
        {
            "$set": {
                "status": "failed",
                "active": False,
                "error": "interrupted",
                "error_detail": "Reset during post-refactor maintenance for a clean retry.",
                "auto_retry_disabled": False,
                "auto_retry_disabled_reason": None,
                "completed_at": now,
                "updated_at": now,
            }
        },
    )
    stats["failed_in_progress"] = reset_in_progress.modified_count
    if reset_in_progress.modified_count:
        print(
            f"[pipeline] marked {reset_in_progress.modified_count} remaining in-progress job(s) failed"
        )

    reset_failed = await db.pipeline_jobs.update_many(
        {
            "status": "failed",
            "auto_retry_disabled": True,
            "error": {"$nin": list(NON_RETRYABLE_ERRORS) + ["deferred"]},
            "auto_retry_disabled_reason": {"$ne": "maintenance: high-attempt defer"},
        },
        {
            "$set": {
                "status": "pending",
                "active": True,
                "steps": FRESH_STEPS,
                "error": None,
                "error_detail": None,
                "attempts": 0,
                "auto_retry_disabled": False,
                "auto_retry_disabled_reason": None,
                "force_reanalyze": False,
                "started_at": None,
                "completed_at": None,
                "last_heartbeat": None,
                "documents_found": 0,
                "documents_stored": 0,
                "crawl_errors": [],
                "crawl_skip_reasons": [],
                "updated_at": now,
            }
        },
    )
    stats["reset_quarantined"] = reset_failed.modified_count
    if reset_failed.modified_count:
        print(
            f"[pipeline] reset {reset_failed.modified_count} quarantined failed job(s) to pending"
        )

    retryable_failed = await db.pipeline_jobs.update_many(
        {
            "status": "failed",
            "active": False,
            "auto_retry_disabled": {"$ne": True},
            "error": {"$nin": list(NON_RETRYABLE_ERRORS)},
        },
        {
            "$set": {
                "status": "pending",
                "active": True,
                "steps": FRESH_STEPS,
                "error": None,
                "error_detail": None,
                "attempts": 0,
                "started_at": None,
                "completed_at": None,
                "last_heartbeat": None,
                "documents_found": 0,
                "documents_stored": 0,
                "crawl_errors": [],
                "crawl_skip_reasons": [],
                "updated_at": now,
            }
        },
    )
    stats["requeued_failed"] = retryable_failed.modified_count
    if retryable_failed.modified_count:
        print(f"[pipeline] requeued {retryable_failed.modified_count} retryable failed job(s)")

    from src.repositories.pipeline_repository import PipelineRepository

    requeued = await PipelineRepository().requeue_failed_jobs(db)
    stats["requeue_via_repo"] = requeued
    if requeued:
        print(f"[pipeline] repository requeue_failed_jobs: {requeued}")

    return stats


async def _products_needing_backfill(db) -> list[str]:
    with_docs = set(await db.documents.distinct("product_id"))
    intel_ids = set(await db.product_intelligence.distinct("product_id"))
    missing_shell: list[str] = []
    for pid in sorted(with_docs - intel_ids):
        row = await db.products.find_one({"id": pid}, {"slug": 1})
        if row and row.get("slug"):
            missing_shell.append(row["slug"])

    no_overview: list[str] = []
    async for row in db.product_intelligence.find(
        {"$or": [{"overview": {"$exists": False}}, {"overview": None}]},
        {"product_id": 1, "product_slug": 1},
    ):
        if row["product_id"] in with_docs:
            no_overview.append(row["product_slug"])

    return sorted(set(missing_shell + no_overview))


async def _backfill_slugs(db, slugs: list[str], *, skip_overview: bool) -> None:
    from src.analyser import analyse_product_documents, generate_product_overview
    from src.repositories.document_repository import DocumentRepository
    from src.services.product_rollup_service import ProductRollupService
    from src.services.service_factory import create_document_service, create_product_service

    product_svc = create_product_service()
    doc_svc = create_document_service()
    rollup_svc = ProductRollupService(document_repo=DocumentRepository())

    succeeded: list[str] = []
    failed: list[str] = []

    for slug in slugs:
        product = await product_svc.get_product_by_slug(db, slug)
        if not product:
            print(f"[backfill] skip {slug}: product not found")
            failed.append(slug)
            continue
        print(f"[backfill] start {slug}")
        t0 = time.perf_counter()
        try:
            rollup = await rollup_svc.build_product_rollup(
                db, product_id=product.id, product_slug=slug
            )
            print(
                f"  rollup: findings={len(rollup.findings)} conflicts={len(rollup.conflicts)} "
                f"coverage={len(rollup.coverage or [])}"
            )
            if not skip_overview:
                await analyse_product_documents(db, slug, doc_svc)
                overview = await generate_product_overview(
                    db,
                    slug,
                    force_regenerate=True,
                    product_svc=product_svc,
                    document_svc=doc_svc,
                )
                print(
                    f"  overview: risk={overview.risk_score} verdict={overview.verdict} "
                    f"stances={len(overview.topic_stances or [])}"
                )
            print(f"[backfill] done {slug} in {time.perf_counter() - t0:.1f}s")
            succeeded.append(slug)
        except Exception as exc:  # noqa: BLE001 - continue batch on single-product failure
            print(f"[backfill] FAILED {slug}: {exc}")
            failed.append(slug)

    print(f"[backfill] complete: {len(succeeded)} ok, {len(failed)} failed")
    if failed:
        print("  failed: " + ", ".join(failed))


async def _print_queue_summary(db) -> None:
    by_status: dict[str, int] = {}
    async for row in db.pipeline_jobs.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[row["_id"]] = row["n"]
    overviews = await db.product_intelligence.count_documents(
        {"overview": {"$exists": True, "$ne": None}}
    )
    intel_total = await db.product_intelligence.count_documents({})
    print(
        f"[summary] pipeline={sum(by_status.values())} {by_status} "
        f"intelligence={intel_total} with_overview={overviews}"
    )


async def _run(args: argparse.Namespace) -> int:
    if args.use_production:
        uri = os.getenv("PRODUCTION_MONGO_URI")
        if not uri:
            print("PRODUCTION_MONGO_URI is not set")
            return 1
        os.environ["MONGO_URI"] = uri

    from src.core.database import db_session
    from src.core.logging import setup_logging

    setup_logging()
    print(f"=== post-refactor maintenance {datetime.now(UTC).isoformat()} ===")

    async with db_session() as db:
        if not args.only_backfill:
            print("\n--- drop legacy collections ---")
            await _drop_legacy_collections(db)

            print("\n--- unstick pipeline ---")
            await _unstick_pipeline(db)

        if not args.skip_backfill:
            exclude = set(args.exclude or [])
            slugs = list(args.slugs) if args.slugs else await _products_needing_backfill(db)
            slugs = [s for s in slugs if s not in exclude]
            print(f"\n--- backfill {len(slugs)} product(s) ---")
            if exclude:
                print(f"  excluded: {', '.join(sorted(exclude))}")
            if slugs:
                print("  " + ", ".join(slugs))
                await _backfill_slugs(db, slugs, skip_overview=args.skip_overview)
            else:
                print("[backfill] nothing to do")

        print("\n--- final state ---")
        await _print_queue_summary(db)

    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
