"""Cancel active full-crawl jobs for products that already have stored policy docs.

Usage:
    uv run python scripts/cancel_wasteful_crawls.py --production --dry-run
    uv run python scripts/cancel_wasteful_crawls.py --production
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from dotenv import load_dotenv

load_dotenv()

IN_FLIGHT = ("pending", "crawling", "synthesising", "generating_overview")


async def main(*, dry_run: bool, use_production: bool) -> None:
    from src.core.logging import get_logger, setup_logging
    from src.ops.script_env import open_db, resolve_production
    from src.services.pipeline_eligibility import count_policy_documents, product_needs_full_crawl
    from src.services.service_factory import create_product_service

    resolve_production(use_production=use_production)
    if use_production:
        print("Using PRODUCTION_MONGO_URI")

    setup_logging()
    logger = get_logger(__name__)
    product_svc = create_product_service()

    client, db = open_db(prefer_production=use_production)
    try:
        jobs = await db.pipeline_jobs.find(
            {
                "active": True,
                "skip_crawl": {"$ne": True},
                "status": {"$in": list(IN_FLIGHT)},
            }
        ).to_list(length=None)

        cancelled = kept = 0
        print(f"Evaluating {len(jobs)} active full-crawl job(s)...")
        for job in jobs:
            slug = job["product_slug"]
            product = await product_svc.get_product_by_slug(db, slug)
            product_id = product.id if product else job.get("product_id")
            doc_count = await count_policy_documents(db, slug=slug, product_id=product_id)
            if await product_needs_full_crawl(db, slug=slug, product_id=product_id):
                kept += 1
                print(f"  [keep]    {slug} status={job['status']} docs={doc_count}")
                continue

            if dry_run:
                cancelled += 1
                print(f"  [dry-run] {slug} status={job['status']} docs={doc_count} job={job['id']}")
                continue

            now = datetime.now(UTC).replace(tzinfo=None)
            await db.pipeline_jobs.update_one(
                {"id": job["id"]},
                {
                    "$set": {
                        "status": "interrupted",
                        "active": False,
                        "error": "interrupted",
                        "error_detail": (
                            f"Cancelled wasteful full crawl — {doc_count} stored policy doc(s)"
                        ),
                        "updated_at": now,
                        "completed_at": now,
                    }
                },
            )
            cancelled += 1
            logger.info("Cancelled wasteful crawl %s job=%s docs=%d", slug, job["id"], doc_count)
            print(f"  [cancel]  {slug} status={job['status']} docs={doc_count} job={job['id']}")

        print(f"\nDone: cancelled={cancelled}, kept={kept}")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cancel wasteful full-crawl pipeline jobs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, use_production=args.production))
