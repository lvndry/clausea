"""Re-analyse documents dropped by a transient analysis failure.

Usage:
    uv run python scripts/recover_analyses.py <slug> [<slug> ...]
    uv run python scripts/recover_analyses.py --completed   # all completed products

Finds non-'other' documents that have extraction but no analysis — the signature of a
transient LLM failure that exhausted in-run retries — re-runs analysis, persists it, and
invalidates the product overview so it regenerates with the recovered document. Connects
to PRODUCTION_MONGO_URI (falls back to MONGO_URI).
"""

import asyncio
import os
import sys

_prod = os.getenv("PRODUCTION_MONGO_URI")
if _prod:
    os.environ["MONGO_URI"] = _prod

from src.analyser import recover_dropped_analyses  # noqa: E402
from src.core.database import db_session  # noqa: E402
from src.core.logging import setup_logging  # noqa: E402
from src.services.service_factory import (  # noqa: E402
    create_document_service,
    create_product_service,
)


async def main(slugs: list[str]) -> None:
    setup_logging()
    doc_svc = create_document_service()
    product_svc = create_product_service()
    async with db_session() as db:
        if slugs == ["--completed"]:
            jobs = await db.pipeline_jobs.find({"status": "completed"}).to_list(length=500)
            slugs = [j["product_slug"] for j in jobs]
            print(f"recovering across {len(slugs)} completed product(s)")
        total = 0
        for slug in slugs:
            recovered = await recover_dropped_analyses(db, slug, doc_svc, product_svc)
            if recovered:
                print(f"  {slug}: recovered {recovered} document(s)")
            total += recovered
        print(f"done — recovered {total} document(s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: recover_analyses.py <slug> [<slug> ...] | --completed")
        sys.exit(1)
    asyncio.run(main(sys.argv[1:]))
