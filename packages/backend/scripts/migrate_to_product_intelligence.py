#!/usr/bin/env python3
"""Migrate legacy product satellite collections into product_intelligence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from src.models.document import (
    ComplianceBreakdown,
    ConsumerExplainer,
    MetaSummary,
    ProductDeepAnalysis,
)
from src.models.product_intelligence import (
    OverviewSnapshot,
    ProductIntelligence,
    ProductRollup,
    RollupConflict,
    RollupItem,
)
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository


def _hash_overview(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _rollup_from_aggregation(row: dict[str, Any]) -> ProductRollup:
    items = [
        RollupItem(
            category=item["category"],
            value=item["value"],
            document_ids=item.get("documents") or item.get("document_ids") or [],
            attributes=item.get("attributes") or [],
            confidence=item.get("confidence"),
        )
        for item in row.get("findings") or []
    ]
    conflicts = [
        RollupConflict(
            category=c["category"],
            description=c["description"],
            document_ids=c.get("document_ids") or [],
            severity=c.get("severity"),
        )
        for c in row.get("conflicts") or []
    ]
    return ProductRollup(
        coverage=row.get("coverage") or [],
        items=items,
        conflicts=conflicts,
        generated_at=row.get("generated_at") or datetime.now(),
    )


async def migrate(*, dry_run: bool, verify_only: bool) -> None:
    import os

    uri = os.environ.get("MONGO_URI")
    if not uri:
        raise SystemExit("MONGO_URI is required")

    client = AsyncIOMotorClient(uri, tls=True, tlsCAFile=certifi.where())
    db = client["clausea"]
    repo = ProductIntelligenceRepository()

    product_rows = await db.products.find({}, {"id": 1, "slug": 1}).to_list(length=None)
    migrated = 0
    skipped = 0

    for product in product_rows:
        product_id = product["id"]
        product_slug = product["slug"]

        if verify_only:
            existing = await repo.get_by_product_id(db, product_id)
            if existing and existing.overview:
                migrated += 1
            else:
                skipped += 1
            continue

        overview_row = await db.product_overviews.find_one({"product_slug": product_slug})
        aggregation_row = await db.aggregations.find_one({"product_id": product_id})
        explainer_row = await db.product_explainers.find_one({"product_slug": product_slug})
        compliance_row = await db.product_compliance.find_one({"product_slug": product_slug})
        deep_row = await db.deep_analyses.find_one({"product_slug": product_slug})

        if not any([overview_row, aggregation_row, explainer_row, compliance_row, deep_row]):
            skipped += 1
            continue

        intelligence = ProductIntelligence(product_id=product_id, product_slug=product_slug)

        if aggregation_row:
            intelligence.rollup = _rollup_from_aggregation(aggregation_row)
            intelligence.rollup_generated_at = aggregation_row.get("generated_at")

        if overview_row:
            overview_payload = {k: v for k, v in overview_row.items() if k != "_id"}
            intelligence.overview = MetaSummary.model_validate(overview_payload)
            intelligence.overview_generated_at = overview_row.get("updated_at")
            intelligence.overview_history = [
                OverviewSnapshot(
                    overview_hash=_hash_overview(overview_payload),
                    risk_score=overview_row.get("risk_score"),
                    verdict=overview_row.get("verdict"),
                    one_line_summary=overview_row.get("one_line_summary"),
                )
            ]

        if explainer_row:
            payload = {k: v for k, v in explainer_row.items() if k != "_id"}
            intelligence.explainer = ConsumerExplainer.model_validate(payload)

        if compliance_row and compliance_row.get("compliance"):
            intelligence.compliance = {
                regime: ComplianceBreakdown.model_validate(data)
                for regime, data in compliance_row["compliance"].items()
            }

        if deep_row:
            payload = {k: v for k, v in deep_row.items() if k not in {"_id", "document_signature"}}
            intelligence.deep_analysis = ProductDeepAnalysis.model_validate(payload)
            intelligence.deep_analysis_document_signature = deep_row.get("document_signature")

        doc_hashes: dict[str, str] = {}
        async for doc in db.documents.find(
            {"$or": [{"product_id": product_id}, {"product_ids": product_id}]},
            {"id": 1, "content_hash": 1},
        ):
            if doc.get("id") and doc.get("content_hash"):
                doc_hashes[doc["id"]] = doc["content_hash"]
        intelligence.source_hashes = doc_hashes
        intelligence.updated_at = datetime.now()

        if dry_run:
            print(f"[dry-run] would migrate {product_slug}")
        else:
            await repo.upsert(db, intelligence)
            await db.products.update_one(
                {"id": product_id},
                {
                    "$set": {
                        "stats.document_count": len(doc_hashes),
                        "stats.has_overview": intelligence.overview is not None,
                        "stats.risk_score": (
                            intelligence.overview.risk_score if intelligence.overview else None
                        ),
                        "stats.last_indexed_at": intelligence.updated_at,
                    }
                },
            )
            print(f"migrated {product_slug}")
        migrated += 1

    print(f"done: migrated={migrated} skipped={skipped}")
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=args.dry_run, verify_only=args.verify))


if __name__ == "__main__":
    main()
