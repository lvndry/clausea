"""Product service for business logic operations.

This service coordinates business logic and delegates data access
to the ProductRepository. It no longer owns database connections
and instead accepts database instances as parameters.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, ClassVar
from urllib.parse import urlparse

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import (
    ComplianceBreakdown,
    ConsumerExplainer,
    DocumentSummary,
    MetaSummary,
    ProductAnalysis,
    ProductDeepAnalysis,
    ProductOverview,
)
from src.models.product import Product
from src.prompts.analysis_prompts import OVERVIEW_CORE_DOC_TYPES
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_repository import ProductRepository

logger = get_logger(__name__)


class ProductService:
    """Service for product-related business logic.

    This service coordinates business logic and uses repositories for
    data access. It doesn't own database connections - those are passed
    via parameters from the context manager.
    """

    def __init__(
        self,
        product_repo: ProductRepository,
        document_repo: DocumentRepository,
    ) -> None:
        """Initialize ProductService with repository dependencies.

        Args:
            product_repo: Repository for product data access
            document_repo: Repository for document data access
        """
        self._product_repo: ProductRepository = product_repo
        self._document_repo: DocumentRepository = document_repo

    # ============================================================================
    # Product Operations
    # ============================================================================

    async def get_product_by_slug(self, db: AgnosticDatabase, slug: str) -> Product | None:
        """Get a product by its slug.

        Args:
            db: Database instance
            slug: Product slug

        Returns:
            Product or None if not found
        """
        return await self._product_repo.find_by_slug(db, slug)

    async def get_product_by_id(self, db: AgnosticDatabase, product_id: str) -> Product | None:
        """Get a product by its ID.

        Args:
            db: Database instance
            product_id: Product ID

        Returns:
            Product or None if not found
        """
        return await self._product_repo.find_by_id(db, product_id)

    async def get_product_by_domain(self, db: AgnosticDatabase, domain: str) -> Product | None:
        """Get a product by one of its domains.

        Args:
            db: Database instance
            domain: Domain to search for (e.g., "netflix.com", "slack.com")

        Returns:
            Product or None if not found
        """
        return await self._product_repo.find_by_domain(db, domain)

    async def find_by_domain_variant(self, db: AgnosticDatabase, domain: str) -> Product | None:
        """Find a product by domain with base-domain fallback.

        This normalizes the input and falls back to the base domain
        (e.g., "app.slack.com" -> "slack.com", "www.netflix.com" -> "netflix.com").
        """
        if not domain:
            return None

        normalized = self._normalize_domain(domain)
        product = await self._product_repo.find_by_domain(db, normalized)
        if product:
            return product

        base_domain = self._base_domain(normalized)
        if base_domain and base_domain != normalized:
            return await self._product_repo.find_by_domain(db, base_domain)
        return None

    async def create_product(self, db: AgnosticDatabase, product: Product) -> Product:
        """Create a new product.

        Args:
            db: Database instance
            product: Product to create

        Returns:
            The created Product
        """
        return await self._product_repo.create(db, product)

    async def update_product_name(
        self,
        db: AgnosticDatabase,
        product_id: str,
        name: str,
        name_source: str | None = None,
    ) -> None:
        """Update the display name of a product.

        Replaces the domain-derived placeholder name (e.g. "Openai") with the canonical
        brand name extracted from page metadata (e.g. "OpenAI"). ``name_source`` records
        provenance so a manually-curated or already-improved name is never overwritten.
        """
        await self._product_repo.update_name(db, product_id, name, name_source=name_source)

    async def get_all_products(self, db: AgnosticDatabase) -> list[Product]:
        """Get all products.

        Args:
            db: Database instance

        Returns:
            List of all products
        """
        all_products: list[Product] = await self._product_repo.find_all(db)
        return all_products

    async def get_products_with_documents(self, db: AgnosticDatabase) -> list[Product]:
        """Get all products that have at least one document.

        Args:
            db: Database instance

        Returns:
            List of products that have documents
        """
        products: list[Product] = await self._product_repo.find_all_with_documents(db)
        return products

    async def get_products_paginated(
        self,
        db: AgnosticDatabase,
        *,
        page: int,
        limit: int,
        search: str = "",
    ) -> tuple[list[Product], int]:
        skip = (page - 1) * limit
        return await self._product_repo.find_paginated(db, skip=skip, limit=limit, search=search)

    async def delete_product_cascade(self, db: AgnosticDatabase, product_id: str) -> dict[str, Any]:
        """Delete a product and all its related data across collections.

        Returns counts of deleted records per collection, or ``{"error": ...}`` if the product
        does not exist.
        """
        product = await self._product_repo.find_by_id(db, product_id)
        if not product:
            return {"error": "Product not found"}

        counts: dict[str, Any] = {}

        # Shared-document semantics: unlink this product from canonical documents and
        # delete only rows that are not linked to any remaining product.
        linked_docs = await db.documents.find(
            {"$or": [{"product_id": product_id}, {"product_ids": product_id}]},
            {"id": 1, "product_id": 1, "product_ids": 1},
        ).to_list(length=None)
        documents_deleted = 0
        documents_unlinked = 0
        for row in linked_docs:
            doc_id = row.get("id")
            if not doc_id:
                continue
            linked_ids: list[str] = []
            primary = row.get("product_id")
            if isinstance(primary, str) and primary:
                linked_ids.append(primary)
            product_ids = row.get("product_ids")
            if isinstance(product_ids, list):
                for candidate in product_ids:
                    if isinstance(candidate, str) and candidate and candidate not in linked_ids:
                        linked_ids.append(candidate)
            remaining_ids = [pid for pid in linked_ids if pid != product_id]
            if remaining_ids:
                await db.documents.update_one(
                    {"id": doc_id},
                    {
                        "$set": {
                            "product_id": remaining_ids[0],
                            "product_ids": remaining_ids,
                            "updated_at": datetime.now(),
                        }
                    },
                )
                documents_unlinked += 1
            else:
                await db.documents.delete_one({"id": doc_id})
                documents_deleted += 1
        counts["documents"] = documents_deleted + documents_unlinked
        counts["documents_deleted"] = documents_deleted
        counts["documents_unlinked"] = documents_unlinked

        result = await db.pipeline_jobs.delete_many({"product_slug": product.slug})
        counts["pipeline_jobs"] = result.deleted_count

        result = await db.product_intelligence.delete_many({"product_id": product_id})
        counts["product_intelligence"] = result.deleted_count

        result = await db.document_changes.delete_many({"product_id": product_id})
        counts["document_changes"] = result.deleted_count

        session_docs = await db.crawl_sessions.find({"product_id": product_id}, {"id": 1}).to_list(
            length=None
        )
        session_ids = [s["id"] for s in session_docs if s.get("id")]
        if session_ids:
            result = await db.crawl_events.delete_many({"session_id": {"$in": session_ids}})
            counts["crawl_events"] = result.deleted_count
            result = await db.crawl_targets.delete_many({"session_id": {"$in": session_ids}})
            counts["crawl_targets"] = result.deleted_count
        else:
            counts["crawl_events"] = 0
            counts["crawl_targets"] = 0

        result = await db.crawl_sessions.delete_many({"product_id": product_id})
        counts["crawl_sessions"] = result.deleted_count

        result = await db.products.delete_one({"id": product_id})
        counts["products"] = result.deleted_count

        return counts

    # ============================================================================
    # Product Overview Storage Operations
    # ============================================================================

    async def delete_product_overview(self, db: AgnosticDatabase, slug: str) -> None:
        """Delete the stored product overview for a product.

        Args:
            db: Database instance
            slug: Product slug
        """
        await self._product_repo.delete_product_overview(db, slug)

    async def count_analyzed_products(self, db: AgnosticDatabase) -> int:
        """Count products with a completed analysis (a stored overview)."""
        return await self._product_repo.count_products_with_overview(db)

    async def list_analyzed_products_for_sitemap(
        self, db: AgnosticDatabase
    ) -> list[dict[str, Any]]:
        """Slug + last-updated for every product with a completed overview (sitemap)."""
        return await self._product_repo.list_analyzed_overviews(db)

    async def get_product_overview_data(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        """Get the stored product overview data for a product.

        Args:
            db: Database instance
            product_slug: Product slug

        Returns:
            Dictionary with 'overview' key, or None
        """
        overview_data: dict[str, Any] | None = await self._product_repo.get_product_overview(
            db, product_slug
        )
        return overview_data

    async def save_product_overview(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        meta_summary: MetaSummary,
        job_id: str | None = None,
        product_id: str | None = None,
        thin_evidence: bool = False,
        thin_evidence_reason: str | None = None,
    ) -> None:
        """Save the product overview payload to the database.

        Args:
            db: Database instance
            product_slug: Product slug
            meta_summary: Overview payload (MetaSummary shape)
            job_id: Optional pipeline job that produced this overview
            product_id: Product identifier for the owning product record
            thin_evidence: When True, overview is stored without a consumer grade
            thin_evidence_reason: Human-readable reason grading was withheld
        """
        await self._product_repo.save_product_overview(
            db,
            product_slug,
            meta_summary,
            job_id=job_id,
            product_id=product_id,
            thin_evidence=thin_evidence,
            thin_evidence_reason=thin_evidence_reason,
        )

    # ============================================================================
    # Consumer Explainer Storage (product-level, consumer-facing)
    # ============================================================================

    async def get_product_explainer(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        """Get the product-level consumer explainer with canonical grade.

        Product pages treat overview scoring as the single source of truth.
        The explainer grade is therefore reconciled against product_intelligence overview data
        before returning, and legacy mismatches are repaired best-effort.
        Stored explainers also get verified source citations backfilled on read
        from the product's core document extractions when missing.
        """
        explainer = await self._product_repo.get_product_explainer(db, product_slug)
        if not explainer:
            return None

        explainer = await self._enrich_product_explainer_citations(db, product_slug, explainer)

        canonical_grade = await self._get_canonical_overview_grade(db, product_slug)
        if canonical_grade is None:
            return explainer

        current_grade = self._coerce_grade(explainer.get("grade"))
        current_reason = explainer.get("grade_reason") or ""
        grade_mismatch = current_grade != canonical_grade
        reason_stale = self._is_grade_reason_stale(current_reason, canonical_grade)

        if not grade_mismatch and not reason_stale:
            return explainer

        if grade_mismatch:
            logger.info(
                "Canonicalizing product explainer grade for %s: %s -> %s",
                product_slug,
                current_grade or "unknown",
                canonical_grade,
            )
            canonical_reason = self._grade_reason_from_overview(canonical_grade, explainer)
        else:
            logger.info(
                "Repairing stale grade_reason for %s (grade=%s)",
                product_slug,
                canonical_grade,
            )
            canonical_reason = self._GRADE_REASONS.get(
                canonical_grade, "Risk assessment based on structured policy analysis."
            )

        repaired = dict(explainer)
        repaired["grade"] = canonical_grade
        repaired["grade_reason"] = canonical_reason

        try:
            await self._product_repo.update_product_explainer_grade(
                db, product_slug, canonical_grade, grade_reason=canonical_reason
            )
        except Exception as exc:  # noqa: BLE001 - best-effort repair
            logger.warning(
                "Failed to persist canonical explainer grade for %s: %s",
                product_slug,
                exc,
            )
        return repaired

    async def _enrich_product_explainer_citations(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        explainer: dict[str, Any],
    ) -> dict[str, Any]:
        """Backfill missing source citations for legacy stored explainers."""
        product = await self._product_repo.find_by_slug(db, product_slug)
        if not product:
            return explainer

        documents = await self._document_repo.find_by_product_id_full(db, product.id)
        core_docs = [
            document
            for document in documents
            if document.doc_type in OVERVIEW_CORE_DOC_TYPES and document.extraction is not None
        ]
        if not core_docs:
            return explainer

        try:
            from src.analyser import enrich_consumer_explainer_citations

            explainer_model = ConsumerExplainer.model_validate(explainer)
            enriched = enrich_consumer_explainer_citations(explainer_model, core_docs)
            return enriched.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - best-effort enrichment
            logger.warning(
                "Failed to enrich explainer citations for %s: %s",
                product_slug,
                exc,
            )
            return explainer

    async def save_product_explainer(
        self, db: AgnosticDatabase, product_slug: str, explainer: ConsumerExplainer
    ) -> bool:
        """Persist the product-level consumer explainer; True when it landed.

        The grade is always derived from the canonical overview score when an
        overview exists, so explainer-owned grading cannot diverge.
        """
        canonical_grade = await self._get_canonical_overview_grade(db, product_slug)
        payload = explainer

        if canonical_grade is not None:
            current_grade = self._coerce_grade(explainer.grade)
            if current_grade != canonical_grade:
                canonical_reason = self._grade_reason_from_overview(canonical_grade, explainer)
                logger.info(
                    "Overriding explainer grade with canonical overview grade for %s: %s -> %s",
                    product_slug,
                    current_grade or "unknown",
                    canonical_grade,
                )
                payload = explainer.model_copy(
                    update={"grade": canonical_grade, "grade_reason": canonical_reason}
                )
            elif self._is_grade_reason_stale(explainer.grade_reason or "", canonical_grade):
                canonical_reason = self._GRADE_REASONS.get(
                    canonical_grade, "Risk assessment based on structured policy analysis."
                )
                logger.info(
                    "Clearing stale grade_reason for %s (grade=%s)",
                    product_slug,
                    canonical_grade,
                )
                payload = explainer.model_copy(update={"grade_reason": canonical_reason})

        return await self._product_repo.save_product_explainer(db, product_slug, payload)

    async def get_product_compliance(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        """Get the stored per-regime compliance breakdown ({regime: {...}}), or None."""
        return await self._product_repo.get_product_compliance(db, product_slug)

    async def save_product_compliance(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        compliance: dict[str, ComplianceBreakdown],
    ) -> bool:
        """Persist the per-regime compliance breakdown; True when it landed."""
        return await self._product_repo.save_product_compliance(db, product_slug, compliance)

    # ============================================================================
    # Deep Analysis Storage Operations
    # ============================================================================

    async def get_deep_analysis(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        """Get the stored deep analysis data for a product.

        Args:
            db: Database instance
            product_slug: Product slug

        Returns:
            Dictionary with 'deep_analysis' and 'document_signature' keys, or None
        """
        deep_analysis_data: dict[str, Any] | None = await self._product_repo.get_deep_analysis(
            db, product_slug
        )
        return deep_analysis_data

    async def save_deep_analysis(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        deep_analysis: ProductDeepAnalysis,
        document_signature: str,
    ) -> None:
        """Save the deep analysis to the database with document signature.

        Args:
            db: Database instance
            product_slug: Product slug
            deep_analysis: ProductDeepAnalysis object to save
            document_signature: Hash signature of all document contents
        """
        await self._product_repo.save_deep_analysis(
            db, product_slug, deep_analysis, document_signature
        )

    # ============================================================================
    # Business Logic Methods (Level 1, 2, 3 Analysis)
    # ============================================================================

    async def get_product_overview(
        self,
        db: AgnosticDatabase,
        slug: str,
        product: Product | None = None,
    ) -> ProductOverview | None:
        """Get the Level 1 overview for a product.

        This is business logic that transforms cached data into a user-facing overview.

        Args:
            db: Database instance
            slug: Product slug
            product: Pre-fetched product to avoid a duplicate lookup (optional)

        Returns:
            ProductOverview or None if not available
        """
        overview_data = await self._product_repo.get_product_overview(db, slug)
        if not overview_data:
            return None
        meta_summary = MetaSummary(**overview_data["overview"])

        # Fetch product info if not provided by caller
        if product is None:
            product = await self._product_repo.find_by_slug(db, slug)

        # Compute document counts and types in parallel — independent queries
        document_counts = None
        document_types = None
        if product:
            document_counts, document_types = await asyncio.gather(
                self._product_repo.get_document_counts(db, product.id),
                self._product_repo.get_document_types(db, product.id),
            )

        # Extract updated_at from overview payload if present
        updated_at = None
        if "updated_at" in overview_data["overview"]:
            try:
                updated_at = datetime.fromisoformat(overview_data["overview"]["updated_at"])
            except Exception:
                pass

        overview = self._transform_to_overview(meta_summary, slug, updated_at)

        # Override product name with real name when available
        if product:
            overview.product_name = product.name
            overview.company_name = product.company_name

        # Attach optional fields from meta_summary and computed values
        overview.keypoints = meta_summary.keypoints
        overview.document_counts = document_counts
        overview.document_types = document_types

        # Attach new structured fields for Overview redesign
        overview.data_collection_details = meta_summary.data_collection_details
        overview.third_party_details = meta_summary.third_party_details

        # If compliance_status is missing from meta summary, aggregate from document analyses
        if not overview.compliance_status and product:
            compliance_maps = await self._document_repo.get_compliance_status_by_product(
                db, product.id
            )
            aggregated_compliance: dict[str, list[int]] = {}
            for compliance_status in compliance_maps:
                for reg, score in compliance_status.items():
                    if score is not None:
                        aggregated_compliance.setdefault(reg, []).append(score)
            if aggregated_compliance:
                overview.compliance_status = {
                    reg: round(sum(scores) / len(scores))
                    for reg, scores in aggregated_compliance.items()
                }

        stored_compliance = await self._product_repo.get_product_compliance(db, slug)
        if stored_compliance:
            parsed: dict[str, ComplianceBreakdown] = {}
            for regime, payload in stored_compliance.items():
                if not isinstance(payload, dict):
                    continue
                try:
                    parsed[str(regime)] = ComplianceBreakdown.model_validate(payload, strict=False)
                except Exception:
                    continue
            overview.compliance = parsed or None

        from src.services.citation_filter import filter_topic_stance_citations

        if overview.topic_stances:
            overview.topic_stances = filter_topic_stance_citations(overview.topic_stances)

        return overview

    async def get_product_analysis(self, db: AgnosticDatabase, slug: str) -> ProductAnalysis | None:
        """Get the Level 2 full analysis for a product.

        Args:
            db: Database instance
            slug: Product slug

        Returns:
            ProductAnalysis or None if not available
        """
        overview_data = await self._product_repo.get_product_overview(db, slug)
        if not overview_data:
            return None
        meta_summary = MetaSummary(**overview_data["overview"])

        # Extract updated_at from overview payload if present
        updated_at = None
        if "updated_at" in overview_data["overview"]:
            try:
                updated_at = datetime.fromisoformat(overview_data["overview"]["updated_at"])
            except Exception:
                pass

        overview = self._transform_to_overview(meta_summary, slug, updated_at)

        # Fetch documents
        product = await self._product_repo.find_by_slug(db, slug)
        documents: list[DocumentSummary] = []
        if product:
            docs = await self._document_repo.find_by_product_id_full(db, product.id)
            documents = [DocumentSummary.from_document(doc) for doc in docs]

        # Justified per-regime compliance (score + status + strengths/gaps), produced by
        # the pipeline's compliance step. Pydantic coerces the stored {regime: {...}} dicts
        # into ComplianceBreakdown objects.
        compliance = await self._product_repo.get_product_compliance(db, slug)

        return ProductAnalysis(
            overview=overview,
            detailed_scores=meta_summary.scores,
            compliance=compliance,
            all_keypoints=meta_summary.keypoints,
            documents=documents,
        )

    async def get_product_documents(self, db: AgnosticDatabase, slug: str) -> list[DocumentSummary]:
        """Get the list of documents for a product.

        Args:
            db: Database instance
            slug: Product slug

        Returns:
            List of document summaries
        """
        product = await self._product_repo.find_by_slug(db, slug)
        if not product:
            return []

        docs = await self._document_repo.find_by_product_id_with_analysis(db, product.id)
        return [DocumentSummary.from_document(doc) for doc in docs]

    async def get_product_deep_analysis(
        self, db: AgnosticDatabase, slug: str
    ) -> ProductDeepAnalysis | None:
        """Get the Level 3 deep analysis for a product.

        Args:
            db: Database instance
            slug: Product slug

        Returns:
            ProductDeepAnalysis or None if not available
        """
        stored_data = await self._product_repo.get_deep_analysis(db, slug)
        if not stored_data:
            return None

        try:
            deep_analysis: ProductDeepAnalysis = ProductDeepAnalysis.model_validate(
                stored_data["deep_analysis"]
            )
            return deep_analysis
        except Exception as e:
            logger.error(f"Failed to parse deep analysis for {slug}: {e}")
            return None

    # ============================================================================
    # Helper Methods
    # ============================================================================

    def _transform_to_overview(
        self, meta: MetaSummary, slug: str, updated_at: datetime | None = None
    ) -> ProductOverview:
        """Transform a MetaSummary into a ProductOverview.

        This is pure business logic with no database access.

        Args:
            meta: MetaSummary object
            slug: Product slug
            updated_at: Last updated timestamp

        Returns:
            ProductOverview object
        """
        return ProductOverview(
            product_name=slug.capitalize(),  # Placeholder, ideally fetch from Product
            product_slug=slug,
            company_name=None,  # Will be set from Product if available
            last_updated=updated_at if updated_at else datetime.now(),
            verdict=meta.verdict,
            grade=meta.grade,
            grade_justification=meta.grade_justification,
            one_line_summary=meta.summary,
            headline_claim=meta.headline_claim,
            data_collected=meta.data_collected,
            data_purposes=meta.data_purposes,
            your_rights=meta.your_rights,
            dangers=meta.dangers,
            benefits=meta.benefits,
            recommended_actions=meta.recommended_actions,
            # Sub-scores breakdown
            detailed_scores=meta.scores,
            # Compliance status (aggregated from document-level analyses)
            compliance_status=meta.compliance_status,
            # Quick-scan privacy signals
            privacy_signals=meta.privacy_signals,
            topic_stances=meta.topic_stances,
            coverage=meta.coverage,
            contract_clauses=meta.contract_clauses,
        )

    @staticmethod
    def _coerce_grade(raw_grade: Any) -> str | None:
        if not isinstance(raw_grade, str):
            return None
        candidate = raw_grade.strip().upper()[:1]
        if candidate in {"A", "B", "C", "D", "E"}:
            return candidate
        return None

    async def _get_canonical_overview_grade(
        self, db: AgnosticDatabase, product_slug: str
    ) -> str | None:
        overview_data = await self._product_repo.get_product_overview(db, product_slug)
        overview = overview_data.get("overview") if overview_data else None
        if not isinstance(overview, dict):
            return None
        return self._coerce_grade(overview.get("grade"))

    _GRADE_REASONS: ClassVar[dict[str, str]] = {
        "A": "Very user-friendly: minimal data collection, strong user controls, no major concerns.",
        "B": "Generally user-friendly: some concerns but good transparency and user rights overall.",
        "C": "Moderate risk: notable concerns around data sharing, limited user controls, or vague language.",
        "D": "Pervasive risk: significant issues with data practices, limited user rights, or broad data sharing.",
        "E": "Very pervasive risk: critical concerns such as forced arbitration, broad data selling, or severe opacity.",
    }

    # Matches phrases like "base grade is C" or "base grade is D" in grade_reason text.
    _STALE_GRADE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"\bbase grade is ([A-E])\b", re.IGNORECASE
    )

    @classmethod
    def _is_grade_reason_stale(cls, grade_reason: str, expected_grade: str) -> bool:
        """Return True when grade_reason references a different base grade than expected."""
        match = cls._STALE_GRADE_RE.search(grade_reason)
        if match:
            return match.group(1).upper() != expected_grade.upper()
        return False

    @classmethod
    def _grade_reason_from_overview(
        cls,
        canonical_grade: str,
        explainer: ConsumerExplainer | dict,
        *,
        overview_grade_justification: str | None = None,
    ) -> str:
        """Build a canonical grade_reason that explains the overview-derived grade."""
        if overview_grade_justification and overview_grade_justification.strip():
            return overview_grade_justification.strip()

        canonical_justification = cls._GRADE_REASONS.get(
            canonical_grade, "Risk assessment based on structured policy analysis."
        )
        original_reason = (
            explainer.grade_reason
            if isinstance(explainer, ConsumerExplainer)
            else explainer.get("grade_reason", "")
        )
        if original_reason and original_reason != canonical_justification:
            return f"{canonical_justification} Original assessment: {original_reason}"
        return canonical_justification

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        candidate = domain.strip().lower()
        if "://" not in candidate and "/" in candidate:
            candidate = "https://" + candidate
        if "://" in candidate:
            parsed = urlparse(candidate)
            candidate = parsed.netloc or parsed.path
        if candidate.startswith("www."):
            candidate = candidate[4:]
        return candidate

    @staticmethod
    def _base_domain(domain: str) -> str:
        parts = domain.split(".")
        two_part_tlds = {"co.uk", "com.au", "co.nz", "co.jp", "com.br", "co.in"}

        if len(parts) >= 3:
            potential_tld = ".".join(parts[-2:])
            if potential_tld in two_part_tlds:
                return ".".join(parts[-3:])
            return ".".join(parts[-2:])
        return domain
