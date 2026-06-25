"""Queue full crawl+analysis pipeline jobs.

Default: only products with **no stored policy documents**. Products with docs
should use ``requeue_analysis.py`` instead.

Usage:
    uv run python scripts/requeue_crawl.py --production --dry-run
    uv run python scripts/requeue_crawl.py --production
    uv run python scripts/requeue_crawl.py --production openai
    uv run python scripts/requeue_crawl.py --production --all   # all products (careful)
"""

from __future__ import annotations

import argparse
import asyncio

from dotenv import load_dotenv

load_dotenv()


async def main(
    slugs: list[str] | None,
    *,
    dry_run: bool,
    use_production: bool,
    queue_all: bool,
    missing_overviews_only: bool,
) -> None:
    from src.core.database import db_session
    from src.core.logging import get_logger, setup_logging
    from src.models.pipeline_job import PipelineJob
    from src.ops.script_env import job_url, resolve_production
    from src.repositories.pipeline_repository import PipelineRepository
    from src.services.pipeline_eligibility import has_overview, product_needs_full_crawl
    from src.services.service_factory import create_product_service

    resolve_production(use_production=use_production)
    if use_production:
        print("Using PRODUCTION_MONGO_URI")

    setup_logging()
    logger = get_logger(__name__)
    product_svc = create_product_service()
    pipeline_repo = PipelineRepository()

    async with db_session() as db:
        if slugs:
            target_slugs = slugs
        else:
            rows = await db.products.find({}, {"slug": 1}).to_list(length=None)
            target_slugs = sorted(row["slug"] for row in rows if row.get("slug"))

        queued = skipped_active = skipped_analysis_pending = 0
        skipped_has_docs = skipped_has_overview = skipped_missing = 0

        mode = "all products" if queue_all or slugs else "needs full crawl (no stored policy docs)"
        print(f"Evaluating {len(target_slugs)} product(s) — mode: {mode}...")
        for slug in target_slugs:
            product = await product_svc.get_product_by_slug(db, slug)
            if not product:
                skipped_missing += 1
                print(f"  [missing] {slug}")
                continue

            if not queue_all and not slugs:
                if not await product_needs_full_crawl(db, slug=slug, product_id=product.id):
                    skipped_has_docs += 1
                    continue
                if missing_overviews_only and await has_overview(db, slug):
                    skipped_has_overview += 1
                    continue

            active = await pipeline_repo.find_active_by_product_slug(db, slug)
            if active:
                if active.skip_crawl and active.status == "pending":
                    skipped_analysis_pending += 1
                    print(f"  [analysis] {slug} (job {active.id})")
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
                url=job_url(product),
                skip_crawl=False,
                force_reanalyze=True,
            )
            stored_job, created = await pipeline_repo.find_or_create_active(db, job)
            if created:
                queued += 1
                logger.info("Queued full crawl %s job=%s", slug, stored_job.id)
                print(f"  [queued]  {slug} job={stored_job.id}")
            else:
                skipped_active += 1
                print(f"  [active]  {slug} (job {stored_job.id}, status={stored_job.status})")

        print(
            f"\nDone: queued={queued}, skipped_active={skipped_active}, "
            f"skipped_has_docs={skipped_has_docs}, skipped_has_overview={skipped_has_overview}, "
            f"skipped_analysis_pending={skipped_analysis_pending}, skipped_missing={skipped_missing}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Queue full crawl+analysis pipeline jobs")
    parser.add_argument("slugs", nargs="*", help="Product slugs (default: needs-crawl only)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--all", action="store_true", help="Ignore stored-doc check")
    parser.add_argument("--missing-overviews", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        main(
            args.slugs or None,
            dry_run=args.dry_run,
            use_production=args.production,
            queue_all=args.all,
            missing_overviews_only=args.missing_overviews,
        )
    )
