#!/usr/bin/env python3
"""Ship-readiness health check for Clausea's analysis pipeline.

Read-only diagnostic. Queries the live MongoDB and prints a single-screen
status report covering the five ship-readiness gates defined in
docs/superpowers/specs/2026-05-25-ship-readiness-design.md.

Usage:
    uv run python scripts/ship_health_check.py
    uv run python scripts/ship_health_check.py --json

Exit code:
    0  all five ship gates green (SHIP_FOUNDATION_GREEN)
    1  at least one gate red
    2  could not query the database
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.core.database import db_session  # noqa: E402

# Ship-readiness thresholds (mirrored from the design doc).
MIN_PRODUCTS_WITH_OVERVIEW = 30
MAX_OVERVIEWS_MISSING_REQUIRED_FIELDS = 0
MAX_DOCUMENTS_WITH_EMPTY_TEXT = 0
MAX_PIPELINE_FAILURE_RATE = 0.10
EMPTY_TEXT_THRESHOLD_CHARS = 500
PIPELINE_LOOKBACK_DAYS = 7

# Fields on the stored MetaSummary in product_intelligence.overview.
# The API later transforms summary → one_line_summary (product_service.py:475).
# We measure the underlying storage shape, not the API shape.
REQUIRED_OVERVIEW_FIELDS = (
    "summary",
    "verdict",
    "keypoints",
    "data_collected",
    "your_rights",
    "dangers",
)


async def collect_metrics() -> dict[str, Any]:
    """Run all the read-only queries and assemble the report payload."""
    async with db_session() as db:
        products_total = await db.products.count_documents({})
        documents_total = await db.documents.count_documents({})

        # Coverage gates.
        products_with_documents = len(await db.documents.distinct("product_id"))
        product_overview_count = await db.product_intelligence.count_documents(
            {"overview": {"$exists": True, "$ne": None}}
        )

        # Empty-text documents — a doc that crawled but holds no real policy text.
        documents_with_empty_text = await db.documents.count_documents(
            {
                "$or": [
                    {"text": {"$exists": False}},
                    {"text": ""},
                    {"text": None},
                    {
                        "$expr": {
                            "$lt": [
                                {"$strLenCP": {"$ifNull": ["$text", ""]}},
                                EMPTY_TEXT_THRESHOLD_CHARS,
                            ]
                        }
                    },
                ]
            }
        )

        # Overviews missing required fields.
        overviews_missing_fields: list[dict[str, Any]] = []
        async for ov in db.product_intelligence.find(
            {"overview": {"$exists": True, "$ne": None}},
            {"product_slug": 1, "overview": 1},
        ):
            overview = ov.get("overview") or {}
            missing = [f for f in REQUIRED_OVERVIEW_FIELDS if not overview.get(f)]
            if missing:
                overviews_missing_fields.append(
                    {"product_slug": ov.get("product_slug"), "missing": missing}
                )

        # Pipeline jobs in the last N days.
        lookback = datetime.now(UTC) - timedelta(days=PIPELINE_LOOKBACK_DAYS)
        jobs_recent = await db.pipeline_jobs.count_documents({"updated_at": {"$gte": lookback}})
        jobs_recent_failed = await db.pipeline_jobs.count_documents(
            {"updated_at": {"$gte": lookback}, "status": "failed"}
        )
        jobs_recent_completed = await db.pipeline_jobs.count_documents(
            {"updated_at": {"$gte": lookback}, "status": "completed"}
        )

        # Top failure reasons (across all time — recent samples are sparse).
        error_counter: Counter[str] = Counter()
        async for job in db.pipeline_jobs.find(
            {"status": "failed"}, {"error": 1, "product_slug": 1}
        ):
            err = (job.get("error") or "unknown")[:120]
            error_counter[err] += 1

        # Orphaned running jobs older than 30 minutes.
        orphan_cutoff = datetime.now(UTC) - timedelta(minutes=30)
        orphaned_running = await db.pipeline_jobs.count_documents(
            {"status": "running", "updated_at": {"$lt": orphan_cutoff}}
        )

        # Per-stage signal: how many documents have analysis vs extraction.
        docs_with_extraction = await db.documents.count_documents({"extraction": {"$ne": None}})
        docs_with_analysis = await db.documents.count_documents({"analysis": {"$ne": None}})

    failure_rate = jobs_recent_failed / jobs_recent if jobs_recent else 0.0

    gates = {
        "products_with_overview": {
            "value": product_overview_count,
            "threshold": f">= {MIN_PRODUCTS_WITH_OVERVIEW}",
            "green": product_overview_count >= MIN_PRODUCTS_WITH_OVERVIEW,
        },
        "overviews_missing_required_fields": {
            "value": len(overviews_missing_fields),
            "threshold": f"== {MAX_OVERVIEWS_MISSING_REQUIRED_FIELDS}",
            "green": len(overviews_missing_fields) <= MAX_OVERVIEWS_MISSING_REQUIRED_FIELDS,
        },
        "documents_with_empty_text": {
            "value": documents_with_empty_text,
            "threshold": f"== {MAX_DOCUMENTS_WITH_EMPTY_TEXT} (< {EMPTY_TEXT_THRESHOLD_CHARS} chars)",
            "green": documents_with_empty_text <= MAX_DOCUMENTS_WITH_EMPTY_TEXT,
        },
        "pipeline_failure_rate_7d": {
            "value": round(failure_rate, 3),
            "threshold": f"< {MAX_PIPELINE_FAILURE_RATE}",
            "green": failure_rate < MAX_PIPELINE_FAILURE_RATE if jobs_recent else False,
            "note": "no recent jobs" if not jobs_recent else None,
        },
        "no_orphaned_running_jobs": {
            "value": orphaned_running,
            "threshold": "== 0 older than 30 min",
            "green": orphaned_running == 0,
        },
    }

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "totals": {
            "products_total": products_total,
            "documents_total": documents_total,
            "products_with_documents": products_with_documents,
            "documents_with_extraction": docs_with_extraction,
            "documents_with_analysis": docs_with_analysis,
            "products_with_overview": product_overview_count,
        },
        "pipeline_jobs_last_7d": {
            "total": jobs_recent,
            "failed": jobs_recent_failed,
            "completed": jobs_recent_completed,
            "failure_rate": round(failure_rate, 3),
        },
        "top_failure_reasons": error_counter.most_common(10),
        "overviews_missing_fields": overviews_missing_fields,
        "orphaned_running_jobs": orphaned_running,
        "gates": gates,
        "all_green": all(g["green"] for g in gates.values()),
    }


def format_human(report: dict[str, Any]) -> str:
    """Render the report as a single-screen status block."""
    out: list[str] = []
    out.append("=" * 72)
    out.append("Clausea Ship-Readiness Health Check")
    out.append(report["timestamp"])
    out.append("=" * 72)

    t = report["totals"]
    out.append("")
    out.append("Catalog")
    out.append(f"  products_total           : {t['products_total']}")
    out.append(f"  products_with_documents  : {t['products_with_documents']}")
    out.append(f"  documents_total          : {t['documents_total']}")
    out.append(f"  documents_with_extraction: {t['documents_with_extraction']}")
    out.append(f"  documents_with_analysis  : {t['documents_with_analysis']}")
    out.append(f"  products_with_overview   : {t['products_with_overview']}")

    pj = report["pipeline_jobs_last_7d"]
    out.append("")
    out.append(f"Pipeline jobs (last {PIPELINE_LOOKBACK_DAYS}d)")
    out.append(
        f"  total: {pj['total']:>3}  completed: {pj['completed']:>3}  "
        f"failed: {pj['failed']:>3}  failure_rate: {pj['failure_rate']}"
    )

    if report["top_failure_reasons"]:
        out.append("")
        out.append("Top failure reasons (all time)")
        for reason, count in report["top_failure_reasons"]:
            out.append(f"  [{count:>3}x] {reason}")

    if report["overviews_missing_fields"]:
        out.append("")
        out.append("Overviews missing required fields")
        for ov in report["overviews_missing_fields"]:
            out.append(f"  {ov['product_slug']}: missing {', '.join(ov['missing'])}")

    if report["orphaned_running_jobs"]:
        out.append("")
        out.append(f"Orphaned `running` jobs > 30 min: {report['orphaned_running_jobs']}")

    out.append("")
    out.append("Ship gates")
    for name, gate in report["gates"].items():
        symbol = "GREEN" if gate["green"] else "RED  "
        note = f" ({gate['note']})" if gate.get("note") else ""
        out.append(f"  [{symbol}] {name:<36} = {gate['value']:<8} (need {gate['threshold']}){note}")

    out.append("")
    if report["all_green"]:
        out.append("SHIP_FOUNDATION_GREEN")
    else:
        out.append("NOT SHIP-READY")
    out.append("=" * 72)
    return "\n".join(out)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args()

    try:
        report = await collect_metrics()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not collect metrics: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, default=str, indent=2))
    else:
        print(format_human(report))

    return 0 if report["all_green"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
