"""Queue analysis-only pipeline jobs (synthesis + overview, no recrawl).

Usage:
    uv run python scripts/requeue_analysis.py --production --dry-run
    uv run python scripts/requeue_analysis.py --production
    uv run python scripts/requeue_analysis.py --production tiktok capcut
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
) -> None:
    from src.core.database import db_session
    from src.core.logging import get_logger, setup_logging
    from src.models.pipeline_job import PipelineJob
    from src.ops.script_env import job_url, resolve_production
    from src.repositories.pipeline_repository import PipelineRepository
    from src.services.pipeline_eligibility import count_policy_documents
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
            cursor = db.product_intelligence.find(
                {"overview": {"$exists": True, "$ne": None}},
                {"product_slug": 1},
            )
            rows = await cursor.to_list(length=None)
            target_slugs = sorted(row["product_slug"] for row in rows if row.get("product_slug"))

        queued = skipped_active = skipped_no_docs = skipped_missing = 0
        print(f"Evaluating {len(target_slugs)} product(s)...")
        for slug in target_slugs:
            product = await product_svc.get_product_by_slug(db, slug)
            if not product:
                skipped_missing += 1
                print(f"  [missing] {slug}")
                continue

            doc_count = await count_policy_documents(db, slug=slug, product_id=product.id)
            if doc_count == 0:
                skipped_no_docs += 1
                print(f"  [no-docs] {slug}")
                continue

            if dry_run:
                print(f"  [dry-run] {slug} ({doc_count} docs)")
                queued += 1
                continue

            job = PipelineJob(
                product_slug=slug,
                product_id=product.id,
                product_name=product.name,
                url=job_url(product),
                skip_crawl=True,
                force_reanalyze=True,
            )
            stored_job, created = await pipeline_repo.find_or_create_active(db, job)
            if created:
                queued += 1
                logger.info(
                    "Queued analysis-only %s job=%s docs=%d", slug, stored_job.id, doc_count
                )
                print(f"  [queued]  {slug} job={stored_job.id} docs={doc_count}")
            else:
                skipped_active += 1
                print(f"  [active]  {slug} (job {stored_job.id}, status={stored_job.status})")

        print(
            f"\nDone: queued={queued}, skipped_active={skipped_active}, "
            f"skipped_no_docs={skipped_no_docs}, skipped_missing={skipped_missing}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Queue analysis-only pipeline jobs")
    parser.add_argument("slugs", nargs="*", help="Product slugs (default: all with overviews)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.slugs or None, dry_run=args.dry_run, use_production=args.production))
