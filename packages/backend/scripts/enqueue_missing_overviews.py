"""Queue pipeline jobs for products missing a completed product_overviews record.

Uses PipelineService.create_job_for_product so jobs target the correct product
slug even when crawl URLs resolve to a different domain (e.g. Apple Music).

Usage:
    uv run python scripts/enqueue_missing_overviews.py              # dry-run (default)
    uv run python scripts/enqueue_missing_overviews.py --execute  # enqueue jobs

Production (injects MONGO_URI from linked Railway service):
    railway run --service api uv run python scripts/enqueue_missing_overviews.py --execute
"""

from __future__ import annotations

import argparse
import asyncio

from src.core.database import db_session
from src.core.logging import setup_logging
from src.services.service_factory import create_pipeline_service


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enqueue pipeline jobs for products without product_overviews."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create pending jobs (default is dry-run only)",
    )
    return parser.parse_args()


async def _missing_overview_products(db) -> list[dict]:
    cursor = db.products.aggregate(
        [
            {
                "$lookup": {
                    "from": "product_overviews",
                    "localField": "slug",
                    "foreignField": "product_slug",
                    "as": "overview",
                }
            },
            {"$match": {"overview": {"$size": 0}}},
            {
                "$project": {
                    "slug": 1,
                    "name": 1,
                    "domains": 1,
                    "crawl_base_urls": 1,
                }
            },
            {"$sort": {"slug": 1}},
        ]
    )
    return await cursor.to_list(length=500)


async def _run(args: argparse.Namespace) -> int:
    setup_logging()
    pipeline_svc = create_pipeline_service()

    async with db_session() as db:
        products = await _missing_overview_products(db)
        if not products:
            print("No products missing product_overviews.")
            return 0

        print(f"Found {len(products)} product(s) without product_overviews")
        if not args.execute:
            print("DRY RUN — pass --execute to enqueue jobs")

        enqueued = 0
        skipped_active = 0
        skipped_no_url = 0
        skipped_indexed = 0
        sample_enqueued: list[str] = []
        sample_skipped: list[str] = []

        for product in products:
            slug = product["slug"]
            has_url = bool(product.get("crawl_base_urls") or product.get("domains"))
            if not has_url:
                skipped_no_url += 1
                if len(sample_skipped) < 5:
                    sample_skipped.append(f"{slug} (no crawl URL)")
                print(f"  skip {slug}: no crawl_base_urls or domains")
                continue

            if not args.execute:
                print(f"  would enqueue {slug}")
                enqueued += 1
                if len(sample_enqueued) < 10:
                    sample_enqueued.append(slug)
                continue

            try:
                result = await pipeline_svc.create_job_for_product(db, slug)
            except ValueError as exc:
                skipped_no_url += 1
                if len(sample_skipped) < 5:
                    sample_skipped.append(f"{slug} ({exc})")
                print(f"  skip {slug}: {exc}")
                continue

            if result.get("already_indexed"):
                skipped_indexed += 1
                print(f"  skip {slug}: already indexed")
                continue

            job = result["job"]
            if job.status == "pending":
                enqueued += 1
                if len(sample_enqueued) < 10:
                    sample_enqueued.append(slug)
                print(f"  enqueued {slug}: job={job.id}")
            else:
                skipped_active += 1
                if len(sample_skipped) < 5:
                    sample_skipped.append(f"{slug} (active job {job.status})")
                print(f"  skip {slug}: active job {job.id} status={job.status}")

        pending = await db.pipeline_jobs.count_documents({"status": "pending"})
        crawling = await db.pipeline_jobs.count_documents(
            {"status": {"$in": ["crawling", "summarizing", "generating_overview"]}}
        )
        print()
        print(
            f"summary: missing={len(products)} "
            f"enqueued={enqueued} skipped_active={skipped_active} "
            f"skipped_indexed={skipped_indexed} skipped_no_url={skipped_no_url} "
            f"pending_in_db={pending} in_progress_in_db={crawling}"
        )
        if sample_enqueued:
            print(f"sample enqueued: {', '.join(sample_enqueued)}")
        if sample_skipped:
            print(f"sample skipped: {', '.join(sample_skipped)}")

    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
