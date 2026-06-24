"""Queue full crawl+analysis pipeline jobs (runs after analysis-only backlog).

Creates pending pipeline jobs with skip_crawl=False and force_reanalyze=True.
Skips products that already have an active job (including analysis-only requeues).

Run after analysis-only jobs complete, or alongside them — the worker claims
skip_crawl jobs first, so full crawls wait until the analysis backlog drains.

Usage:
    uv run python scripts/requeue_crawl.py --production --dry-run
    uv run python scripts/requeue_crawl.py --production
    uv run python scripts/requeue_crawl.py --production tiktok
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _resolve_production(use_production: bool) -> None:
    if not use_production:
        return
    prod_uri = os.getenv("PRODUCTION_MONGO_URI")
    if not prod_uri:
        print("ERROR: PRODUCTION_MONGO_URI not set")
        sys.exit(1)
    os.environ["MONGO_URI"] = prod_uri


def _job_url(product) -> str:
    if product.crawl_base_urls:
        return product.crawl_base_urls[0]
    if product.domains:
        return f"https://{product.domains[0]}"
    return f"https://clausea.co/products/{product.slug}"


async def main(
    slugs: list[str] | None,
    *,
    dry_run: bool,
    use_production: bool,
) -> None:
    _resolve_production(use_production)
    if use_production:
        print("Using PRODUCTION_MONGO_URI")

    from src.core.database import db_session
    from src.core.logging import setup_logging
    from src.models.pipeline_job import PipelineJob
    from src.repositories.pipeline_repository import PipelineRepository
    from src.services.service_factory import create_product_service

    setup_logging()
    product_svc = create_product_service()
    pipeline_repo = PipelineRepository()

    async with db_session() as db:
        if slugs:
            target_slugs = slugs
        else:
            rows = await db.products.find({}, {"slug": 1}).to_list(length=None)
            target_slugs = sorted(row["slug"] for row in rows if row.get("slug"))

        queued = 0
        skipped_active = 0
        skipped_analysis_pending = 0
        skipped_missing = 0

        print(f"Evaluating {len(target_slugs)} product(s)...")
        for slug in target_slugs:
            product = await product_svc.get_product_by_slug(db, slug)
            if not product:
                skipped_missing += 1
                print(f"  [missing] {slug}")
                continue

            active = await pipeline_repo.find_active_by_product_slug(db, slug)
            if active:
                if active.skip_crawl and active.status == "pending":
                    skipped_analysis_pending += 1
                    print(f"  [analysis] {slug} (job {active.id} — waiting for analysis-only)")
                else:
                    skipped_active += 1
                    print(f"  [active]  {slug} (job {active.id}, status={active.status})")
                continue

            if dry_run:
                print(f"  [dry-run] {slug}")
                queued += 1
                continue

            job = PipelineJob(
                product_slug=slug,
                product_id=product.id,
                product_name=product.name,
                url=_job_url(product),
                skip_crawl=False,
                force_reanalyze=True,
            )
            stored_job, created = await pipeline_repo.find_or_create_active(db, job)
            if created:
                queued += 1
                print(f"  [queued]  {slug} job={stored_job.id}")
            else:
                skipped_active += 1
                print(f"  [active]  {slug} (job {stored_job.id}, status={stored_job.status})")

        print()
        print(
            f"Done: queued={queued}, skipped_active={skipped_active}, "
            f"skipped_analysis_pending={skipped_analysis_pending}, "
            f"skipped_missing={skipped_missing}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Queue full crawl+analysis pipeline jobs")
    parser.add_argument("slugs", nargs="*", help="Product slugs (default: all products)")
    parser.add_argument("--dry-run", action="store_true", help="List targets without enqueueing")
    parser.add_argument("--production", action="store_true", help="Use PRODUCTION_MONGO_URI")
    args = parser.parse_args()
    asyncio.run(main(args.slugs or None, dry_run=args.dry_run, use_production=args.production))
