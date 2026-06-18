"""Compact end-to-end review of one or more products, for following pipeline output.

Usage:
    uv run python scripts/review_product.py <slug> [<slug> ...]
    uv run python scripts/review_product.py --completed   # all completed jobs

Read-only. Connects to PRODUCTION_MONGO_URI (falls back to MONGO_URI). For each
product it prints a crawl summary, a per-document analysis line, and a single
✅/⚠️ verdict that flags the obvious errors worth acting on: documents stored but
never analysed, region mislabels, empty detector output, and a missing grade.
"""

import asyncio
import os
import sys

_prod = os.getenv("PRODUCTION_MONGO_URI")
if _prod:
    os.environ["MONGO_URI"] = _prod

from src.core.database import db_session  # noqa: E402
from src.core.logging import setup_logging  # noqa: E402
from src.services.service_factory import (  # noqa: E402
    create_document_service,
    create_product_service,
)

_ROW_HINTS = ("row", "outside", "non-eea", "rest of world", "rest-of-world", "global)")


def _region_looks_mislabelled(title: str, url: str, regions: list[str] | None) -> bool:
    blob = f"{title or ''} {url or ''}".lower()
    rest_of_world = any(h in blob for h in _ROW_HINTS)
    regs = [r.lower() for r in (regions or [])]
    return rest_of_world and "eu" in regs and "global" not in regs


async def review(db, product_svc, doc_svc, slug: str) -> None:
    product = await product_svc.get_product_by_slug(db, slug)
    if not product:
        print(f"\n=== {slug} ===\n  (no product)")
        return

    job = await db.pipeline_jobs.find_one({"product_slug": slug})
    docs = await doc_svc.get_product_documents(db, product.id)
    overview = await product_svc.get_product_overview(db, slug, product=product)

    print(f"\n=== {slug} ({product.name}) ===")

    if job:
        skips: dict[str, int] = {}
        for s in job.get("crawl_skip_reasons") or []:
            if not isinstance(s, dict):
                continue
            skips[s.get("reason", "?")] = skips.get(s.get("reason", "?"), 0) + 1
        skip_str = (
            ", ".join(f"{k}={v}" for k, v in sorted(skips.items(), key=lambda x: -x[1])) or "none"
        )
        print(
            f"  crawl: status={job.get('status')} found={job.get('documents_found')} "
            f"stored={job.get('documents_stored')} errors={len(job.get('crawl_errors') or [])}"
        )
        print(f"  skips: {skip_str}")

    issues: list[str] = []
    other_skipped = [d for d in docs if not d.analysis and d.doc_type == "other"]
    real_unanalysed = [d for d in docs if not d.analysis and d.doc_type != "other"]
    region_bad = [d for d in docs if _region_looks_mislabelled(d.title or "", d.url, d.regions)]
    empty_scores = [d for d in docs if d.analysis and not d.analysis.scores]

    print(f"  documents: {len(docs)}  (other-skipped by design: {len(other_skipped)})")
    for d in docs:
        a = d.analysis
        if not a:
            tag = "·other (skip by design)" if d.doc_type == "other" else "⚠️ ANALYSIS FAILED"
            print(f"    - [{d.doc_type}] {(d.title or d.url)[:55]}  {tag}")
            continue
        nclauses = len(a.critical_clauses or [])
        flag = "  ⚠️region" if d in region_bad else ""
        print(
            f"    - [{d.doc_type}] risk={a.risk_score} verdict={a.verdict} "
            f"clauses={nclauses} regions={d.regions}{flag}"
        )

    ov_doc = await db.product_overviews.find_one({"product_slug": slug})
    if overview:
        grade = (ov_doc or {}).get("grade")
        ps = getattr(overview, "privacy_signals", None)
        ndangers = len(getattr(overview, "dangers", None) or [])
        print(
            f"  overview: verdict={overview.verdict} risk={overview.risk_score} "
            f"grade={grade} dangers={ndangers}"
        )
        if ps is None:
            issues.append("overview has no privacy_signals")
    else:
        issues.append("no overview generated")

    if real_unanalysed:
        issues.append(
            f"{len(real_unanalysed)} non-'other' doc(s) ANALYSIS FAILED: "
            + ", ".join((d.title or d.url)[:40] for d in real_unanalysed)
        )
    if region_bad:
        issues.append(
            f"{len(region_bad)} doc(s) region mislabelled: "
            + ", ".join((d.title or d.url)[:40] for d in region_bad)
        )
    if empty_scores:
        issues.append(f"{len(empty_scores)} analysed doc(s) with empty detector scores")
    if not docs:
        issues.append("no documents stored")

    if issues:
        print("  ⚠️ VERDICT: issues —")
        for i in issues:
            print(f"      • {i}")
    else:
        print("  ✅ VERDICT: clean (coverage + analysis + overview all present)")


async def main(slugs: list[str]) -> None:
    setup_logging()
    product_svc = create_product_service()
    doc_svc = create_document_service()
    async with db_session() as db:
        if slugs == ["--completed"]:
            jobs = await db.pipeline_jobs.find({"status": "completed"}).to_list(length=500)
            slugs = [j["product_slug"] for j in jobs]
            print(f"reviewing {len(slugs)} completed product(s): {', '.join(slugs)}")
        for slug in slugs:
            await review(db, product_svc, doc_svc, slug)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: review_product.py <slug> [<slug> ...] | --completed")
        sys.exit(1)
    asyncio.run(main(sys.argv[1:]))
