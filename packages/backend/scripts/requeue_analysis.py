"""Queue analysis-only pipeline jobs (synthesis + overview, no recrawl).

Usage:
    uv run python scripts/requeue_analysis.py --production --dry-run
    uv run python scripts/requeue_analysis.py --production
    uv run python scripts/requeue_analysis.py --production tiktok capcut
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()


def _parse_ts(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str):
        try:
            ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    return ts


async def _stale_overview_slugs(db, *, stale_hours: int) -> list[str]:
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=stale_hours)
    slugs: list[str] = []
    async for row in db.product_intelligence.find(
        {"overview": {"$exists": True, "$ne": None}},
        {"product_slug": 1, "overview_generated_at": 1, "updated_at": 1},
    ):
        slug = row.get("product_slug")
        if not slug:
            continue
        ts = _parse_ts(row.get("overview_generated_at") or row.get("updated_at"))
        if ts is None or ts >= cutoff:
            continue
        slugs.append(slug)
    return sorted(slugs)


async def main(
    slugs: list[str] | None,
    *,
    dry_run: bool,
    use_production: bool,
    stale_hours: int | None,
) -> None:
    from src.core.logging import get_logger, setup_logging
    from src.models.pipeline_job import PipelineJob
    from src.ops.script_env import job_url, open_db, resolve_production
    from src.repositories.pipeline_repository import PipelineRepository
    from src.services.pipeline_eligibility import count_policy_documents, has_overview
    from src.services.service_factory import create_product_service

    resolve_production(use_production=use_production)
    if use_production:
        print("Using PRODUCTION_MONGO_URI")

    setup_logging()
    logger = get_logger(__name__)
    product_svc = create_product_service()
    pipeline_repo = PipelineRepository()

    client, db = open_db(prefer_production=use_production)
    try:
        if slugs:
            target_slugs = slugs
        elif stale_hours is not None:
            target_slugs = await _stale_overview_slugs(db, stale_hours=stale_hours)
            print(f"Stale overview cutoff: {stale_hours}h ({len(target_slugs)} product(s))")
        else:
            missing: list[str] = []
            async for row in db.products.find({}, {"slug": 1}):
                slug = row.get("slug")
                if slug and not await has_overview(db, slug):
                    missing.append(slug)
            target_slugs = sorted(missing)

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
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Queue analysis-only pipeline jobs")
    parser.add_argument("slugs", nargs="*", help="Product slugs (default: all missing overviews)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument(
        "--stale-hours",
        type=int,
        metavar="N",
        help="Queue products whose overview is older than N hours",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.slugs or None,
            dry_run=args.dry_run,
            use_production=args.production,
            stale_hours=args.stale_hours,
        )
    )
