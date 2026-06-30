"""Repository for unified product_intelligence collection."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.models.document import ConsumerExplainer
from src.models.product_intelligence import (
    OverviewSnapshot,
    ProductIntelligence,
    ProductRollup,
    ThinEvidenceFlags,
)
from src.models.topic_report import ProductTopicReport
from src.repositories.base_repository import BaseRepository


def _row_to_intelligence(row: dict[str, Any] | None) -> ProductIntelligence | None:
    if not row:
        return None
    data = dict(row)
    data.pop("_id", None)
    return ProductIntelligence.model_validate(data)


# Fields needed for overview computation — excludes the large rollup, topic_report,
# explainer, and deep_analysis blobs which can be several MB each.
_OVERVIEW_PROJECTION = {
    "_id": 0,
    "product_id": 1,
    "product_slug": 1,
    "thin_evidence": 1,
    "thin_evidence_reason": 1,
    "indexation_error": 1,
    "overview": 1,
    "overview_generated_at": 1,
    "compliance": 1,
}

# Minimal projection for the thin-evidence flag check only.
_THIN_EVIDENCE_PROJECTION = {
    "_id": 0,
    "thin_evidence": 1,
    "thin_evidence_reason": 1,
    "indexation_error": 1,
}

# Cached topic report only — smallest possible read on warm cache hits.
_TOPIC_REPORT_PROJECTION = {
    "_id": 0,
    "topic_report": 1,
}

# Rollup fields needed when topic_report must be computed.
_TOPICS_ROLLUP_PROJECTION = {
    "_id": 0,
    "product_id": 1,
    "product_slug": 1,
    "rollup": 1,
}


class ProductIntelligenceRepository(BaseRepository):
    COLLECTION = "product_intelligence"

    async def get_by_product_id(
        self, db: AgnosticDatabase, product_id: str
    ) -> ProductIntelligence | None:
        row = await db[self.COLLECTION].find_one({"product_id": product_id})
        return _row_to_intelligence(row)

    async def get_by_slug(
        self, db: AgnosticDatabase, product_slug: str
    ) -> ProductIntelligence | None:
        row = await db[self.COLLECTION].find_one({"product_slug": product_slug})
        return _row_to_intelligence(row)

    async def get_thin_evidence_flags(
        self, db: AgnosticDatabase, product_id: str
    ) -> ThinEvidenceFlags | None:
        """Fetch only thin_evidence flags — avoids transferring large rollup/overview blobs."""
        row = await db[self.COLLECTION].find_one(
            {"product_id": product_id}, _THIN_EVIDENCE_PROJECTION
        )
        if not row:
            return None
        return ThinEvidenceFlags.model_validate(row)

    async def get_for_overview(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str | None = None,
        product_slug: str | None = None,
    ) -> ProductIntelligence | None:
        """Fetch only the fields needed for overview computation.

        Excludes rollup, topic_report, explainer, and deep_analysis to avoid
        transferring several MB of data when only overview fields are required.
        """
        if product_id:
            query: dict[str, Any] = {"product_id": product_id}
        elif product_slug:
            query = {"product_slug": product_slug}
        else:
            return None
        row = await db[self.COLLECTION].find_one(query, _OVERVIEW_PROJECTION)
        return _row_to_intelligence(row)

    async def get_topic_report_cached(
        self, db: AgnosticDatabase, product_id: str
    ) -> ProductTopicReport | None:
        """Return a stored topic report without loading rollup/overview/explainer blobs."""
        row = await db[self.COLLECTION].find_one(
            {"product_id": product_id}, _TOPIC_REPORT_PROJECTION
        )
        if not row or not row.get("topic_report"):
            return None
        return ProductTopicReport.model_validate(row["topic_report"])

    async def get_rollup_for_topics(
        self, db: AgnosticDatabase, product_id: str
    ) -> ProductIntelligence | None:
        """Fetch rollup (and ids) needed to compute a topic report on cache miss."""
        row = await db[self.COLLECTION].find_one(
            {"product_id": product_id}, _TOPICS_ROLLUP_PROJECTION
        )
        return _row_to_intelligence(row)

    async def get_for_explainer(
        self, db: AgnosticDatabase, product_slug: str
    ) -> ConsumerExplainer | None:
        """Fetch the stored explainer blob without loading rollup/topic_report/overview."""
        row = await db[self.COLLECTION].find_one(
            {"product_slug": product_slug},
            {"_id": 0, "explainer": 1},
        )
        if not row or not row.get("explainer"):
            return None
        return ConsumerExplainer.model_validate(row["explainer"])

    async def get_overview_grade(self, db: AgnosticDatabase, product_slug: str) -> str | None:
        """Fetch only the canonical overview grade — used by explainer reconciliation."""
        row = await db[self.COLLECTION].find_one(
            {"product_slug": product_slug},
            {"_id": 0, "overview.grade": 1},
        )
        if not row:
            return None
        overview = row.get("overview")
        if not isinstance(overview, dict):
            return None
        grade = overview.get("grade")
        return str(grade) if grade is not None else None

    async def ensure_shell(
        self, db: AgnosticDatabase, *, product_id: str, product_slug: str
    ) -> ProductIntelligence:
        existing = await self.get_by_product_id(db, product_id)
        if existing:
            return existing
        now = datetime.now()
        shell = ProductIntelligence(product_id=product_id, product_slug=product_slug)
        await db[self.COLLECTION].update_one(
            {"product_id": product_id},
            {
                "$setOnInsert": {
                    **shell.model_dump(mode="json"),
                    "generated_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )
        return (await self.get_by_product_id(db, product_id)) or shell

    async def upsert(self, db: AgnosticDatabase, intelligence: ProductIntelligence) -> None:
        data = intelligence.model_dump(mode="json")
        data["updated_at"] = datetime.now()
        await db[self.COLLECTION].update_one(
            {"product_id": intelligence.product_id},
            {"$set": data},
            upsert=True,
        )

    async def upsert_fields(
        self, db: AgnosticDatabase, product_id: str, fields: dict[str, Any]
    ) -> None:
        fields = dict(fields)
        fields["updated_at"] = datetime.now()
        await db[self.COLLECTION].update_one(
            {"product_id": product_id},
            {"$set": fields},
            upsert=True,
        )

    async def upsert_rollup(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str,
        product_slug: str,
        rollup: ProductRollup,
        source_hashes: dict[str, str],
    ) -> None:
        now = datetime.now()
        await db[self.COLLECTION].update_one(
            {"product_id": product_id},
            {
                "$set": {
                    "product_id": product_id,
                    "product_slug": product_slug,
                    "rollup": rollup.model_dump(mode="json"),
                    "source_hashes": source_hashes,
                    "rollup_generated_at": now,
                    "updated_at": now,
                    "topic_report": None,
                },
                "$setOnInsert": {
                    "id": ProductIntelligence(product_id=product_id, product_slug=product_slug).id,
                    "generated_at": now,
                },
            },
            upsert=True,
        )

    async def store_topic_report(
        self, db: AgnosticDatabase, product_id: str, report: ProductTopicReport
    ) -> None:
        """Persist a pre-computed topic report so subsequent reads skip recomputation."""
        await db[self.COLLECTION].update_one(
            {"product_id": product_id},
            {
                "$set": {
                    "topic_report": report.model_dump(mode="json"),
                    "updated_at": datetime.now(),
                }
            },
        )

    async def delete_for_product(self, db: AgnosticDatabase, product_id: str) -> int:
        result = await db[self.COLLECTION].delete_many({"product_id": product_id})
        return result.deleted_count

    async def mark_citations_stale_for_document(
        self, db: AgnosticDatabase, document_id: str
    ) -> int:
        """Flag every overview citation pointing at ``document_id`` as stale.

        Called when a source document is deleted or superseded so that citations
        referencing it are no longer rendered. Matches across all
        ``overview.topic_stances.supporting_citations`` entries and sets
        ``stale: True`` only on the citations whose ``document_id`` matches,
        leaving sibling citations intact. Returns the number of citations marked.
        """
        count_pipeline = [
            {"$match": {"overview.topic_stances.supporting_citations.document_id": document_id}},
            {"$unwind": "$overview.topic_stances"},
            {"$unwind": "$overview.topic_stances.supporting_citations"},
            {"$match": {"overview.topic_stances.supporting_citations.document_id": document_id}},
            {"$count": "total"},
        ]
        cursor = db[self.COLLECTION].aggregate(count_pipeline)
        count_rows = await cursor.to_list(length=None)
        citation_count = count_rows[0]["total"] if count_rows else 0
        if citation_count == 0:
            return 0

        await db[self.COLLECTION].update_many(
            {"overview.topic_stances.supporting_citations.document_id": document_id},
            [
                {
                    "$set": {
                        "overview.topic_stances": {
                            "$map": {
                                "input": "$overview.topic_stances",
                                "as": "stance",
                                "in": {
                                    "$mergeObjects": [
                                        "$$stance",
                                        {
                                            "supporting_citations": {
                                                "$map": {
                                                    "input": "$$stance.supporting_citations",
                                                    "as": "cite",
                                                    "in": {
                                                        "$mergeObjects": [
                                                            "$$cite",
                                                            {
                                                                "stale": {
                                                                    "$cond": [
                                                                        {
                                                                            "$eq": [
                                                                                "$$cite.document_id",
                                                                                document_id,
                                                                            ]
                                                                        },
                                                                        True,
                                                                        "$$cite.stale",
                                                                    ]
                                                                }
                                                            },
                                                        ]
                                                    },
                                                }
                                            }
                                        },
                                    ]
                                },
                            }
                        }
                    }
                }
            ],
        )
        return citation_count

    async def count_with_overview(self, db: AgnosticDatabase) -> int:
        return await db[self.COLLECTION].count_documents(
            {"overview": {"$exists": True, "$ne": None}}
        )

    async def list_overview_history(
        self, db: AgnosticDatabase, product_slug: str, limit: int = 50
    ) -> list[OverviewSnapshot]:
        intelligence = await self.get_by_slug(db, product_slug)
        if not intelligence:
            return []
        return intelligence.overview_history[:limit]

    async def list_sitemap_entries(self, db: AgnosticDatabase) -> list[dict[str, Any]]:
        cursor = db[self.COLLECTION].find(
            {"overview": {"$exists": True, "$ne": None}},
            {"_id": 0, "product_slug": 1, "overview_generated_at": 1, "updated_at": 1},
        )
        rows = await cursor.to_list(length=None)
        return [
            {
                "product_slug": row.get("product_slug"),
                "updated_at": row.get("overview_generated_at") or row.get("updated_at"),
            }
            for row in rows
            if row.get("product_slug")
        ]
