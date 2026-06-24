"""Validate topic-evidence rollout quality gates on selected products.

Checks:
- deterministic topic payload generation (same input -> same payload)
- coverage behavior (missing/not_disclosed topics carry the not_disclosed stance)
- citation completeness for found findings
- drift boundaries between legacy doc score and topic-composed score

Usage:
    uv run python scripts/validate_topic_rollout.py figma github mistralai
    uv run python scripts/validate_topic_rollout.py --use-production figma github mistralai
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Any, cast

from dotenv import load_dotenv

from src.models.document import InsightCategory

load_dotenv()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate topic rollout checks by slug.")
    parser.add_argument("slugs", nargs="+", help="Product slugs to validate")
    parser.add_argument(
        "--use-production",
        action="store_true",
        help="Use PRODUCTION_MONGO_URI instead of local MONGO_URI",
    )
    parser.add_argument(
        "--max-drift",
        type=int,
        default=3,
        help="Maximum acceptable absolute drift between legacy and topic score",
    )
    return parser.parse_args()


@dataclass
class SlugValidation:
    slug: str
    ok: bool
    checks: list[str]
    failures: list[str]


def _topic_rows_for_composition(
    topics: list[dict[str, Any]],
) -> dict[InsightCategory, dict[str, Any]]:
    topic_rows: dict[InsightCategory, dict[str, Any]] = {}
    for topic in topics:
        topic_name = topic.get("topic")
        if not isinstance(topic_name, str):
            continue
        topic_rows[cast(InsightCategory, topic_name)] = {
            "status": topic.get("status"),
            "stance": topic.get("stance"),
        }
    return topic_rows


async def _validate_slug(
    *,
    slug: str,
    db,
    product_svc,
    doc_svc,
    intelligence_repo,
    max_drift: int,
) -> SlugValidation:
    from src.analyser import _weighted_product_risk_score
    from src.models.document import DocumentSummary
    from src.repositories.document_repository import DocumentRepository
    from src.services.rollup_hydration import rollup_to_hydrated
    from src.services.topic_report_service import build_product_topic_report
    from src.services.topic_stance_service import compose_product_risk_from_topics

    checks: list[str] = []
    failures: list[str] = []

    product = await product_svc.get_product_by_slug(db, slug)
    if not product:
        return SlugValidation(
            slug=slug,
            ok=False,
            checks=checks,
            failures=["product not found"],
        )

    intelligence = await intelligence_repo.get_by_slug(db, slug)
    if not intelligence or not intelligence.rollup:
        return SlugValidation(
            slug=slug,
            ok=False,
            checks=checks,
            failures=["product rollup not found"],
        )

    docs = await doc_svc.get_product_documents(db, product.id)
    doc_summaries = [DocumentSummary.from_document(doc) for doc in docs]
    full_docs = await DocumentRepository().find_by_product_id_full(db, product.id)
    hydrated_rollup = rollup_to_hydrated(
        product_id=product.id,
        product_slug=slug,
        rollup=intelligence.rollup,
        documents=full_docs,
    )
    report_a = build_product_topic_report(
        product_slug=slug,
        rollup=hydrated_rollup,
        documents=doc_summaries,
    )
    report_b = build_product_topic_report(
        product_slug=slug,
        rollup=hydrated_rollup,
        documents=doc_summaries,
    )

    payload_a = report_a.model_dump(mode="json")
    payload_b = report_b.model_dump(mode="json")
    if payload_a == payload_b:
        checks.append("deterministic topic payload")
    else:
        failures.append("topic payload is not deterministic")

    # missing/not_disclosed topics must carry the not_disclosed stance.
    invalid_missing_topics = [
        topic
        for topic in report_a.topics
        if topic.status in {"missing", "not_disclosed"} and topic.stance != "not_disclosed"
    ]
    if not invalid_missing_topics:
        checks.append("missing/not_disclosed topics are not_disclosed stance")
    else:
        failures.append(
            f"missing/not_disclosed topics carry a risk stance ({len(invalid_missing_topics)})"
        )

    found_findings = [
        finding
        for topic in report_a.topics
        if topic.status == "found"
        for finding in topic.findings
    ]
    citation_gaps = [finding.value for finding in found_findings if len(finding.citations) == 0]
    if not citation_gaps:
        checks.append("found findings include citations")
    else:
        failures.append(f"citation gaps in found findings ({len(citation_gaps)})")

    product_risk = compose_product_risk_from_topics(
        _topic_rows_for_composition(payload_a["topics"])
    )
    legacy_score = _weighted_product_risk_score(docs)
    if legacy_score is None:
        checks.append("legacy score unavailable (skipped drift check)")
    else:
        drift = abs(product_risk - legacy_score)
        if drift <= max_drift:
            checks.append(f"grade drift within boundary ({drift} <= {max_drift})")
        else:
            failures.append(f"grade drift too high ({drift} > {max_drift})")

    return SlugValidation(
        slug=slug,
        ok=len(failures) == 0,
        checks=checks,
        failures=failures,
    )


async def _run(args: argparse.Namespace) -> int:
    if args.use_production:
        production_uri = os.getenv("PRODUCTION_MONGO_URI")
        if not production_uri:
            print("PRODUCTION_MONGO_URI is not set")
            return 1
        os.environ["MONGO_URI"] = production_uri

    from src.core.database import db_session
    from src.core.logging import setup_logging
    from src.repositories.product_intelligence_repository import ProductIntelligenceRepository
    from src.services.service_factory import create_document_service, create_product_service

    setup_logging()
    product_svc = create_product_service()
    doc_svc = create_document_service()
    intelligence_repo = ProductIntelligenceRepository()

    results: list[SlugValidation] = []
    async with db_session() as db:
        for slug in args.slugs:
            results.append(
                await _validate_slug(
                    slug=slug,
                    db=db,
                    product_svc=product_svc,
                    doc_svc=doc_svc,
                    intelligence_repo=intelligence_repo,
                    max_drift=args.max_drift,
                )
            )

    failures = 0
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"\n[{status}] {result.slug}")
        for check in result.checks:
            print(f"  - {check}")
        for failure in result.failures:
            print(f"  x {failure}")
        if not result.ok:
            failures += 1

    if failures == 0:
        print("\nAll rollout checks passed.")
        return 0
    print(f"\nRollout checks failed for {failures} slug(s).")
    return 1


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
