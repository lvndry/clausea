"""Orchestrates product_intelligence reads, writes, and product stats."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import (
    ComplianceBreakdown,
    ConsumerExplainer,
    MetaSummary,
    ProductDeepAnalysis,
)
from src.models.pipeline_job import PipelineErrorCode
from src.models.product_intelligence import OverviewSnapshot, ProductIntelligence, ProductRollup
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository

logger = get_logger(__name__)

_OVERVIEW_HISTORY_CAP = 20
_TRACKED_OVERVIEW_FIELDS = [
    "grade",
    "verdict",
    "one_line_summary",
    "dangers",
    "keypoints",
    "summary",
]


def _overview_hash(overview_data: dict[str, Any]) -> str:
    payload = json.dumps(overview_data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _changed_overview_fields(prev: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return [field for field in _TRACKED_OVERVIEW_FIELDS if prev.get(field) != current.get(field)]


class ProductIntelligenceService:
    def __init__(
        self,
        intelligence_repo: ProductIntelligenceRepository | None = None,
        document_repo: DocumentRepository | None = None,
    ) -> None:
        self._intelligence_repo = intelligence_repo or ProductIntelligenceRepository()
        self._document_repo = document_repo or DocumentRepository()

    async def get(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str | None = None,
        product_slug: str | None = None,
    ) -> ProductIntelligence | None:
        if product_id:
            return await self._intelligence_repo.get_by_product_id(db, product_id)
        if product_slug:
            return await self._intelligence_repo.get_by_slug(db, product_slug)
        return None

    async def ensure_shell(
        self, db: AgnosticDatabase, *, product_id: str, product_slug: str
    ) -> ProductIntelligence:
        return await self._intelligence_repo.ensure_shell(
            db, product_id=product_id, product_slug=product_slug
        )

    async def compute_source_hashes(self, db: AgnosticDatabase, product_id: str) -> dict[str, str]:
        documents = await self._document_repo.find_by_product_id(db, product_id)
        hashes: dict[str, str] = {}
        for doc in documents:
            if doc.content_hash:
                hashes[doc.id] = doc.content_hash
        return hashes

    async def save_rollup(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str,
        product_slug: str,
        rollup: ProductRollup,
        source_hashes: dict[str, str] | None = None,
    ) -> None:
        hashes = source_hashes or await self.compute_source_hashes(db, product_id)
        await self._intelligence_repo.upsert_rollup(
            db,
            product_id=product_id,
            product_slug=product_slug,
            rollup=rollup,
            source_hashes=hashes,
        )

    async def mark_thin_evidence(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str,
        product_slug: str,
        reason: str,
        job_id: str | None = None,
    ) -> None:
        """Record insufficient evidence and clear stale overview/explainer outputs."""
        now = datetime.now()
        shell = ProductIntelligence(product_id=product_id, product_slug=product_slug)
        await self._intelligence_repo.upsert_fields(
            db,
            product_id,
            {
                "id": shell.id,
                "product_slug": product_slug,
                "thin_evidence": True,
                "thin_evidence_reason": reason,
                "indexation_error": PipelineErrorCode.thin_evidence,
                "overview": None,
                "explainer": None,
                "overview_generated_at": None,
                "generated_at": now,
            },
        )
        if job_id is not None:
            logger.info(
                "Marked thin evidence for %s (job %s): %s",
                product_slug,
                job_id,
                reason,
            )
        else:
            logger.info("Marked thin evidence for %s: %s", product_slug, reason)
        await self.update_product_stats(db, product_id=product_id, product_slug=product_slug)

    async def save_overview(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str,
        product_slug: str,
        meta_summary: MetaSummary,
        job_id: str | None = None,
        thin_evidence: bool = False,
        thin_evidence_reason: str | None = None,
    ) -> None:
        intelligence = await self.ensure_shell(db, product_id=product_id, product_slug=product_slug)
        overview_data = meta_summary.model_dump(mode="json")
        overview_data["product_slug"] = product_slug
        overview_data["product_id"] = product_id

        prev_overview = (
            intelligence.overview.model_dump(mode="json") if intelligence.overview else {}
        )
        overview_hash = _overview_hash(overview_data)
        prev_hash = _overview_hash(prev_overview) if prev_overview else None

        snapshot: OverviewSnapshot | None = None
        if prev_hash != overview_hash:
            grade = overview_data.get("grade")
            prev_grade = prev_overview.get("grade") if prev_overview else None
            grade_order = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
            grade_delta = (
                (grade_order.get(grade, 0) - grade_order.get(prev_grade, 0))
                if (grade and prev_grade)
                else None
            )
            snapshot = OverviewSnapshot(
                overview_hash=overview_hash,
                grade=grade,
                grade_delta=grade_delta,
                verdict=overview_data.get("verdict"),
                one_line_summary=overview_data.get("one_line_summary"),
                changed_overview_fields=_changed_overview_fields(prev_overview, overview_data),
                job_id=job_id,
            )

        history = list(intelligence.overview_history)
        if snapshot is not None:
            history.insert(0, snapshot)
            history = history[:_OVERVIEW_HISTORY_CAP]

        now = datetime.now()
        fields: dict[str, object] = {
            "product_slug": product_slug,
            "overview": meta_summary.model_dump(mode="json"),
            "overview_history": [snapshot.model_dump(mode="json") for snapshot in history],
            "overview_generated_at": now,
            "thin_evidence": thin_evidence,
            "thin_evidence_reason": (thin_evidence_reason or None) if thin_evidence else None,
        }
        if thin_evidence:
            fields["indexation_error"] = PipelineErrorCode.thin_evidence
        await self._intelligence_repo.upsert_fields(db, product_id, fields)
        await self.update_product_stats(db, product_id=product_id, product_slug=product_slug)

    async def save_explainer(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str,
        product_slug: str,
        explainer: ConsumerExplainer,
    ) -> bool:
        intelligence = await self.ensure_shell(db, product_id=product_id, product_slug=product_slug)
        intelligence.explainer = explainer
        intelligence.updated_at = datetime.now()
        await self._intelligence_repo.upsert(db, intelligence)
        return True

    async def save_compliance(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str,
        product_slug: str,
        compliance: dict[str, ComplianceBreakdown],
    ) -> bool:
        intelligence = await self.ensure_shell(db, product_id=product_id, product_slug=product_slug)
        intelligence.compliance = compliance
        intelligence.updated_at = datetime.now()
        await self._intelligence_repo.upsert(db, intelligence)
        return True

    async def save_deep_analysis(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str,
        product_slug: str,
        deep_analysis: ProductDeepAnalysis,
        document_signature: str,
    ) -> None:
        intelligence = await self.ensure_shell(db, product_id=product_id, product_slug=product_slug)
        intelligence.deep_analysis = deep_analysis
        intelligence.deep_analysis_document_signature = document_signature
        intelligence.updated_at = datetime.now()
        await self._intelligence_repo.upsert(db, intelligence)

    async def update_product_stats(
        self, db: AgnosticDatabase, *, product_id: str, product_slug: str
    ) -> None:
        membership = {"$or": [{"product_id": product_id}, {"product_ids": product_id}]}
        document_count = await db.documents.count_documents(membership)
        intelligence = await self.get(db, product_id=product_id)
        has_graded_overview = (
            intelligence is not None
            and intelligence.overview is not None
            and not intelligence.thin_evidence
            and intelligence.overview.grade is not None
        )
        stats: dict[str, Any] = {
            "stats.document_count": document_count,
            "stats.has_overview": has_graded_overview,
            "stats.last_indexed_at": datetime.now(),
            "stats.grade": intelligence.overview.grade if has_graded_overview else None,
        }
        await db.products.update_one({"id": product_id}, {"$set": stats})

    async def delete_for_product(self, db: AgnosticDatabase, product_id: str) -> int:
        return await self._intelligence_repo.delete_for_product(db, product_id)
