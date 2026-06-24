"""Document repository for data access operations."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import (
    CORE_DOC_TYPES,
    ConsumerExplainer,
    Document,
    DocumentAnalysis,
)
from src.repositories.base_repository import BaseRepository

logger = get_logger(__name__)
_DEFAULT_MAX_RESUME_URLS = 5000


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("Invalid %s=%r (must be int), using default=%d", name, raw, default)
        return default


MAX_RECENT_URLS_PER_RESUME = _read_positive_int_env(
    "PIPELINE_RESUME_MAX_RECENT_URLS", _DEFAULT_MAX_RESUME_URLS
)


def _normalize_document_record(document: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a raw document record loaded from the database so it is compatible
    with the current Pydantic models.

    This is primarily used to handle legacy records that may contain values
    which are no longer valid according to the stricter Literal types in
    `DocumentAnalysis` and related models.
    """
    analysis = document.get("analysis")

    if isinstance(analysis, dict):
        verdict = analysis.get("verdict")

        # Allowed verdict values in DocumentAnalysis / MetaSummary / ProductOverview
        allowed_verdicts = {
            "very_user_friendly",
            "user_friendly",
            "moderate",
            "pervasive",
            "very_pervasive",
        }

        # Handle legacy / invalid verdict values gracefully
        if isinstance(verdict, str) and verdict not in allowed_verdicts:
            # Map known legacy values to the closest current category
            if verdict == "caution":
                analysis["verdict"] = "moderate"
            else:
                # For any other unexpected value, fall back to the default by
                # removing the key so Pydantic uses the field default.
                analysis.pop("verdict", None)

        # Fix malformed summary strings that are actually JSON blobs from the LLM
        summary = analysis.get("summary")
        if isinstance(summary, str) and summary.strip().startswith("{"):
            try:
                parsed = json.loads(summary)
                if isinstance(parsed, dict) and "summary" in parsed:
                    analysis["summary"] = str(parsed["summary"]).strip()
            except (json.JSONDecodeError, TypeError):
                # If parsing fails or the string was truncated, we'll leave it
                # as is. The frontend will render whatever string is present.
                pass

        document["analysis"] = analysis

    # Backfill tier relevance for legacy records that predate this field.
    doc_type = document.get("doc_type")
    if doc_type in CORE_DOC_TYPES:
        document["tier_relevance"] = "core"
    else:
        document["tier_relevance"] = "extended"

    # Shared-document compatibility: legacy rows only have product_id while new rows
    # also carry product_ids (all linked products). Always normalize to a deduped list.
    product_id = document.get("product_id")
    linked_ids = document.get("product_ids")
    normalized_ids: list[str] = []
    if isinstance(product_id, str) and product_id.strip():
        normalized_ids.append(product_id.strip())
    if isinstance(linked_ids, list):
        for value in linked_ids:
            if not isinstance(value, str):
                continue
            candidate = value.strip()
            if candidate and candidate not in normalized_ids:
                normalized_ids.append(candidate)
    if normalized_ids:
        document["product_ids"] = normalized_ids

    return document


def _merge_product_ids(
    *,
    canonical_product_id: str | None,
    linked_product_ids: list[str] | None,
    extra_product_ids: list[str] | None = None,
) -> list[str]:
    merged: list[str] = []
    for candidate in [
        canonical_product_id,
        *list(linked_product_ids or []),
        *list(extra_product_ids or []),
    ]:
        if not isinstance(candidate, str):
            continue
        normalized = candidate.strip()
        if normalized and normalized not in merged:
            merged.append(normalized)
    return merged


def _product_membership_query(product_id: str) -> dict[str, Any]:
    return {"$or": [{"product_id": product_id}, {"product_ids": product_id}]}


def _product_scoped_query(product_id: str, query: dict[str, Any]) -> dict[str, Any]:
    return {"$and": [query, _product_membership_query(product_id)]}


def _contextualize_document_for_product(
    document: dict[str, Any], product_id: str
) -> dict[str, Any]:
    normalized = _normalize_document_record(dict(document))
    normalized["product_ids"] = _merge_product_ids(
        canonical_product_id=normalized.get("product_id"),
        linked_product_ids=normalized.get("product_ids"),
        extra_product_ids=[product_id],
    )
    # Downstream per-product synthesis/finding generation expects document.product_id
    # to be the current product context.
    normalized["product_id"] = product_id
    return normalized


class DocumentRepository(BaseRepository):
    """Repository for document-related database operations.

    Handles all database access for documents and their analyses.
    Methods are stateless and accept database instance as parameter.
    """

    # ============================================================================
    # Document CRUD Operations
    # ============================================================================

    async def find_all(self, db: AgnosticDatabase) -> list[Document]:
        """Get all documents from the database.

        Args:
            db: Database instance

        Returns:
            List of all documents
        """
        documents: list[dict[str, Any]] = await db.documents.find().to_list(length=None)
        return [Document(**_normalize_document_record(document)) for document in documents]

    async def find_by_id(self, db: AgnosticDatabase, document_id: str) -> Document | None:
        """Get a document by its ID.

        Args:
            db: Database instance
            document_id: Document ID

        Returns:
            Document or None if not found
        """
        document = await db.documents.find_one({"id": document_id})
        if not document:
            return None
        return Document(**_normalize_document_record(document))

    async def find_by_url(self, db: AgnosticDatabase, url: str) -> Document | None:
        """Get a document by its URL.

        Args:
            db: Database instance
            url: Document URL

        Returns:
            Document or None if not found
        """
        document = await db.documents.find_one({"url": url})
        if not document:
            return None
        return Document(**_normalize_document_record(document))

    async def find_by_product_and_url(
        self, db: AgnosticDatabase, product_id: str, url: str
    ) -> Document | None:
        """Get a document by URL when linked to the given product."""
        document = await db.documents.find_one(_product_scoped_query(product_id, {"url": url}))
        if not document:
            return None
        return Document(**_contextualize_document_for_product(document, product_id))

    async def find_by_product_and_content_hash(
        self, db: AgnosticDatabase, product_id: str, content_hash: str
    ) -> Document | None:
        """Find an existing document for the same product with matching content hash.

        Used for cross-run deduplication of regional URL variants that serve
        identical content (e.g. apple.com/au/legal vs apple.com/ca/legal).
        Prefers the most-canonical URL (non-locale first).
        """
        from src.pipeline.helpers import _canonical_rank

        query = {
            "$or": [
                {"product_id": product_id},
                {"product_ids": product_id},
            ],
            "content_hash": content_hash,
            "markdown": {"$ne": ""},
        }
        cursor = db.documents.find(query).sort("url", 1)
        candidates = await cursor.to_list(length=10)
        if not candidates:
            return None
        best = min(candidates, key=lambda d: _canonical_rank(d.get("url", "")))
        return Document(**_normalize_document_record(best))

    async def find_by_product_id(self, db: AgnosticDatabase, product_id: str) -> list[Document]:
        """Get all documents for a specific product (listing / light reads).

        Excludes heavy fields (markdown, analysis, extraction) from MongoDB.
        Missing ``markdown`` is filled with an empty string for model validation.

        Args:
            db: Database instance
            product_id: Product ID

        Returns:
            List of documents for the product
        """
        projection = {"markdown": 0, "analysis": 0, "extraction": 0}
        documents: list[dict[str, Any]] = await db.documents.find(
            _product_membership_query(product_id), projection
        ).to_list(length=None)
        for document in documents:
            document.setdefault("markdown", "")
        return [
            Document(**_contextualize_document_for_product(document, product_id))
            for document in documents
        ]

    async def find_by_product_id_full(
        self, db: AgnosticDatabase, product_id: str
    ) -> list[Document]:
        """Get all documents for a product including full body and analysis (pipelines, summaries)."""
        documents: list[dict[str, Any]] = await db.documents.find(
            _product_membership_query(product_id)
        ).to_list(length=None)
        return [
            Document(**_contextualize_document_for_product(document, product_id))
            for document in documents
        ]

    async def find_by_product_id_with_analysis(
        self, db: AgnosticDatabase, product_id: str
    ) -> list[Document]:
        """Get all documents with analysis, excluding heavy body fields (markdown, extraction).

        Use this when DocumentSummary fields are needed but the raw text/markdown is not —
        avoids transferring large body fields over the wire.
        """
        projection = {"markdown": 0, "extraction": 0}
        documents: list[dict[str, Any]] = await db.documents.find(
            _product_membership_query(product_id), projection
        ).to_list(length=None)
        for document in documents:
            document.setdefault("markdown", "")
        return [
            Document(**_contextualize_document_for_product(document, product_id))
            for document in documents
        ]

    async def get_compliance_status_by_product(
        self, db: AgnosticDatabase, product_id: str
    ) -> list[dict[str, int]]:
        """Return only the compliance_status maps for a product's documents.

        Tight projection — pulls only ``analysis.compliance_status`` from each document, avoiding
        the cost of streaming full document bodies just to aggregate one nested field.
        """
        projection = {"_id": 0, "analysis.compliance_status": 1}
        rows: list[dict[str, Any]] = await db.documents.find(
            _product_scoped_query(product_id, {"analysis.compliance_status": {"$exists": True}}),
            projection,
        ).to_list(length=None)
        return [
            row["analysis"]["compliance_status"]
            for row in rows
            if row.get("analysis", {}).get("compliance_status")
        ]

    async def find_by_type(self, db: AgnosticDatabase, doc_type: str) -> list[Document]:
        """Get all documents of a specific type.

        Args:
            db: Database instance
            doc_type: Document type

        Returns:
            List of documents of the specified type
        """
        documents: list[dict[str, Any]] = await db.documents.find({"doc_type": doc_type}).to_list(
            length=None
        )
        return [Document(**_normalize_document_record(document)) for document in documents]

    async def find_with_analysis(
        self, db: AgnosticDatabase, product_id: str | None = None
    ) -> list[Document]:
        """Get documents that have analysis data.

        Args:
            db: Database instance
            product_id: Optional product ID to filter by

        Returns:
            List of documents with analysis
        """
        query: dict[str, Any] = {"analysis": {"$exists": True, "$ne": None}}
        if product_id:
            query = {"$and": [query, _product_membership_query(product_id)]}

        documents: list[dict[str, Any]] = await db.documents.find(query).to_list(length=None)
        if product_id:
            return [
                Document(**_contextualize_document_for_product(document, product_id))
                for document in documents
            ]
        return [Document(**_normalize_document_record(document)) for document in documents]

    async def find_recent_urls_by_product(
        self, db: AgnosticDatabase, product_id: str, cutoff: datetime
    ) -> list[str]:
        """Return URLs of a product's documents written at or after ``cutoff``.

        Backs crawl resume: a retried crawl skips re-fetching docs stored within the
        freshness window. Matches on ``updated_at`` (stamped on every store/update) and
        falls back to ``created_at`` so legacy rows written before ``updated_at`` existed
        are still recognised. Projects only the URL so this stays a cheap, one-per-crawl
        query rather than streaming full document bodies.
        """
        query: dict[str, Any] = {
            "$and": [
                _product_membership_query(product_id),
                {
                    "$or": [
                        {"updated_at": {"$gte": cutoff}},
                        {"created_at": {"$gte": cutoff}},
                    ]
                },
            ]
        }
        rows: list[dict[str, Any]] = (
            await db.documents.find(query, {"_id": 0, "url": 1})
            .sort([("updated_at", -1), ("created_at", -1)])
            .to_list(length=MAX_RECENT_URLS_PER_RESUME)
        )
        if len(rows) == MAX_RECENT_URLS_PER_RESUME:
            logger.warning(
                "Resume URL cap reached for product_id=%s (cap=%d). "
                "Older recent URLs were truncated this run.",
                product_id,
                MAX_RECENT_URLS_PER_RESUME,
            )
        return [row["url"] for row in rows if row.get("url")]

    # ============================================================================
    # Document Persistence Operations
    # ============================================================================

    async def save(self, db: AgnosticDatabase, document: Document) -> Document:
        """Store a document in the database.

        Refuses to persist a Document whose ``markdown`` is effectively empty.
        Such inserts created the 40-empty-doc graveyard in the past — a Document
        with no source text is useless for analysis and masks crawl bugs by
        looking superficially valid in MongoDB. Callers that legitimately need
        to store empty content (none today) should catch ValueError explicitly.

        Args:
            db: Database instance
            document: Document to store

        Returns:
            The stored document

        Raises:
            ValueError: If markdown is empty / whitespace.
            Exception: If storage fails for other reasons.
        """
        if not (document.markdown or "").strip():
            raise ValueError(
                f"Refusing to store empty document {document.id} for url={document.url} "
                f"(markdown is empty — fix upstream extraction instead "
                f"of persisting a placeholder)."
            )
        try:
            document_dict = document.model_dump()
            document_dict["product_ids"] = _merge_product_ids(
                canonical_product_id=document.product_id,
                linked_product_ids=document_dict.get("product_ids"),
            )
            await db.documents.insert_one(document_dict)
            logger.info(
                "Stored document %s for product %s (linked=%s)",
                document.id,
                document.product_id,
                document_dict["product_ids"],
            )
            return document
        except Exception as e:
            logger.error(f"Error storing document {document.id}: {e}")
            raise e

    async def link_to_product(
        self, db: AgnosticDatabase, document_id: str, product_id: str
    ) -> bool:
        """Link an existing canonical document to another product."""
        existing = await db.documents.find_one(
            {"id": document_id}, {"product_id": 1, "product_ids": 1}
        )
        if not existing:
            return False
        merged = _merge_product_ids(
            canonical_product_id=existing.get("product_id"),
            linked_product_ids=existing.get("product_ids"),
            extra_product_ids=[product_id],
        )
        result = await db.documents.update_one(
            {"id": document_id},
            {"$set": {"product_ids": merged, "updated_at": datetime.now()}},
        )
        if result.matched_count == 0:
            return False
        logger.info("Linked document %s to product %s", document_id, product_id)
        return True

    async def update(self, db: AgnosticDatabase, document: Document) -> bool:
        """Update a document in the database.

        Defensive: callers that load a Document via a projecting reader
        (e.g. find_by_product_id strips text/markdown/analysis/extraction and
        replaces them with "" / None) and then $set the full model_dump would
        wipe the stored source text, analysis, and extraction. To prevent that
        class of round-trip data loss, this method drops the empty/None fields
        from the update payload when the stored row already has content, and
        logs a warning so the misuse stays visible.

        Args:
            db: Database instance
            document: Document to update

        Returns:
            True if document was updated, False otherwise

        Raises:
            Exception: If update fails
        """
        try:
            document_dict = document.model_dump()
            incoming_markdown = document_dict.get("markdown") or ""
            guarded_fields = ("analysis", "extraction", "consumer_explainer")
            projection = {
                "markdown": 1,
                "product_id": 1,
                "product_ids": 1,
                **dict.fromkeys(guarded_fields, 1),
            }
            existing = await db.documents.find_one({"id": document.id}, projection)
            if not existing:
                logger.warning(f"No document found with id {document.id} to update")
                return False

            # Preserve canonical owner and merge all linked products. Product-scoped reads
            # may contextualize document.product_id to the current product; writing that
            # value back must not reassign canonical ownership.
            canonical_product_id = existing.get("product_id")
            merged_product_ids = _merge_product_ids(
                canonical_product_id=canonical_product_id,
                linked_product_ids=existing.get("product_ids"),
                extra_product_ids=[
                    document_dict.get("product_id"),
                    *list(document_dict.get("product_ids") or []),
                ],
            )
            if isinstance(canonical_product_id, str) and canonical_product_id.strip():
                document_dict["product_id"] = canonical_product_id.strip()
            document_dict["product_ids"] = merged_product_ids

            # Guard against round-trip wipes: a projecting reader strips heavy fields
            # to None/"" before this Document was built, so writing the full model_dump
            # back would null out stored content. Drop any heavy field from the $set
            # when it is empty incoming but non-empty stored.
            needs_guard = not incoming_markdown or any(
                document_dict.get(field) is None for field in guarded_fields
            )
            if needs_guard:
                if not incoming_markdown and (existing.get("markdown") or ""):
                    document_dict.pop("markdown", None)
                    logger.warning(
                        "DocumentRepository.update refused to overwrite non-empty "
                        f"markdown for document {document.id} with an empty value."
                    )
                for field in guarded_fields:
                    if document_dict.get(field) is None and existing.get(field) is not None:
                        document_dict.pop(field, None)
                        logger.warning(
                            "DocumentRepository.update refused to overwrite non-empty "
                            f"{field} for document {document.id} with None "
                            "(caller likely loaded via a projecting reader)."
                        )

            result = await db.documents.update_one({"id": document.id}, {"$set": document_dict})
            success = result.matched_count > 0
            return bool(success)
        except Exception as e:
            logger.error(f"Error updating document {document.id}: {e}")
            raise e

    async def delete(self, db: AgnosticDatabase, document_id: str) -> bool:
        """Delete a document from the database.

        Before deletion, invalidates any overview citations pointing at this
        document so the product overview does not render orphan sources.

        Args:
            db: Database instance
            document_id: ID of document to delete

        Returns:
            True if document was deleted, False otherwise

        Raises:
            Exception: If deletion fails
        """
        try:
            from src.repositories.product_intelligence_repository import (
                ProductIntelligenceRepository,
            )

            try:
                stale_count = (
                    await ProductIntelligenceRepository().mark_citations_stale_for_document(
                        db, document_id
                    )
                )
                if stale_count:
                    logger.info(
                        "Marked %d overview citation(s) stale for deleted document %s",
                        stale_count,
                        document_id,
                    )
            except Exception as cite_error:  # noqa: BLE001
                logger.warning(
                    "Failed to mark citations stale for document %s: %s",
                    document_id,
                    cite_error,
                )

            result = await db.documents.delete_one({"id": document_id})
            success = result.deleted_count > 0
            if success:
                logger.info(f"Deleted document {document_id}")
            else:
                logger.warning(f"No document found with id {document_id} to delete")
            return bool(success)
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            raise e

    # ============================================================================
    # Analysis Operations
    # ============================================================================

    async def update_analysis(
        self, db: AgnosticDatabase, document_id: str, analysis: DocumentAnalysis
    ) -> bool:
        """Update the analysis for a specific document.

        Args:
            db: Database instance
            document_id: Document ID
            analysis: DocumentAnalysis object

        Returns:
            True if analysis was updated, False otherwise

        Raises:
            Exception: If update fails
        """
        try:
            result = await db.documents.update_one(
                {"id": document_id},
                {"$set": {"analysis": analysis.model_dump(), "updated_at": datetime.now()}},
            )
            # matched_count, not modified_count: re-analysing a document can produce a
            # byte-identical analysis, which Mongo reports as modified_count == 0. The
            # caller treats False as a persistence failure, so success must mean "the
            # document exists and now holds this analysis", i.e. the filter matched.
            success = result.matched_count > 0
            if success:
                logger.info(f"Updated analysis for document {document_id}")
            else:
                logger.warning(f"No document found with id {document_id} to update analysis for")
            return bool(success)
        except Exception as e:
            logger.error(f"Error updating analysis for document {document_id}: {e}")
            raise e

    async def update_consumer_explainer(
        self, db: AgnosticDatabase, document_id: str, explainer: ConsumerExplainer
    ) -> bool:
        """Surgically persist the consumer explainer for one document.

        Uses ``matched_count`` (not ``modified_count``) so re-persisting an
        identical explainer still reports success — the row exists and is
        up to date, which is what callers care about.

        Returns:
            True if a document with ``document_id`` was matched, False otherwise.
        """
        try:
            result = await db.documents.update_one(
                {"id": document_id},
                {
                    "$set": {
                        "consumer_explainer": explainer.model_dump(),
                        "updated_at": datetime.now(),
                    }
                },
            )
            success = result.matched_count > 0
            if success:
                logger.info(f"Updated consumer explainer for document {document_id}")
            else:
                logger.warning(
                    f"No document found with id {document_id} to update consumer explainer"
                )
            return bool(success)
        except Exception as e:
            logger.error(f"Error updating consumer explainer for document {document_id}: {e}")
            raise e
