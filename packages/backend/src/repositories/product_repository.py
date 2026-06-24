"""Product repository for data access operations."""

from __future__ import annotations

import asyncio
import re
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
from src.models.product import Product
from src.repositories.base_repository import BaseRepository
from src.repositories.product_intelligence_repository import ProductIntelligenceRepository
from src.services.product_intelligence_service import ProductIntelligenceService

logger = get_logger(__name__)


def _product_document_membership_query(product_id: str) -> dict[str, Any]:
    return {"$or": [{"product_id": product_id}, {"product_ids": product_id}]}


class ProductRepository(BaseRepository):
    """Repository for product-related database operations.

    Handles all database access for products, meta-summaries, and deep analyses.
    Methods are stateless and accept database instance as parameter.
    """

    # ============================================================================
    # Product CRUD Operations
    # ============================================================================

    async def find_by_slug(self, db: AgnosticDatabase, slug: str) -> Product | None:
        """Get a product by its slug.

        Args:
            db: Database instance
            slug: Product slug

        Returns:
            Product or None if not found
        """
        product_data = await db.products.find_one({"slug": slug})
        if not product_data:
            return None
        return Product(**product_data)

    async def find_by_id(self, db: AgnosticDatabase, product_id: str) -> Product | None:
        """Get a product by its ID.

        Args:
            db: Database instance
            product_id: Product ID

        Returns:
            Product or None if not found
        """
        product_data = await db.products.find_one({"id": product_id})
        if not product_data:
            return None
        return Product(**product_data)

    async def find_by_domain(self, db: AgnosticDatabase, domain: str) -> Product | None:
        """Get a product by one of its domains.

        Args:
            db: Database instance
            domain: Domain to search for (e.g., "netflix.com", "slack.com")

        Returns:
            Product or None if not found
        """
        # Search for domain in the domains array
        product_data = await db.products.find_one({"domains": domain})
        if not product_data:
            return None
        return Product(**product_data)

    async def create(self, db: AgnosticDatabase, product: Product) -> Product:
        """Create a new product.

        Args:
            db: Database instance
            product: Product to create

        Returns:
            The created Product
        """
        await db.products.insert_one(product.model_dump())
        logger.debug(f"Created product {product.slug}")
        return product

    async def add_crawl_seeds(self, db: AgnosticDatabase, product_id: str, urls: list[str]) -> None:
        """Append URLs to crawl_base_urls, ignoring duplicates already present."""
        await db.products.update_one(
            {"id": product_id},
            {"$addToSet": {"crawl_base_urls": {"$each": urls}}},
        )

    async def update_name(
        self,
        db: AgnosticDatabase,
        product_id: str,
        name: str,
        name_source: str | None = None,
    ) -> None:
        """Update the display name of a product.

        Used after a crawl to replace the domain-derived name with the canonical
        brand name extracted from page metadata (e.g. og:site_name). ``name_source``
        records the provenance so the pipeline knows not to overwrite a name that
        has already been improved or was manually curated.
        """
        update: dict[str, Any] = {"name": name}
        if name_source is not None:
            update["name_source"] = name_source
        await db.products.update_one(
            {"id": product_id},
            {"$set": update},
        )
        logger.debug(
            "Updated product name for %s to '%s' (source=%s)", product_id, name, name_source
        )

    async def find_all(self, db: AgnosticDatabase) -> list[Product]:
        """Get all products.

        Args:
            db: Database instance

        Returns:
            List of all products
        """
        products_data: list[dict[str, Any]] = await db.products.find().to_list(length=None)
        return [Product(**product_data) for product_data in products_data]

    async def find_all_with_documents(self, db: AgnosticDatabase) -> list[Product]:
        """Get all products that have at least one document.

        Args:
            db: Database instance

        Returns:
            List of products that have documents
        """
        # Use aggregation to find distinct linked product_ids from canonical documents.
        pipeline = [
            {
                "$project": {
                    "linked_product_ids": {
                        "$concatArrays": [
                            {
                                "$cond": [
                                    {"$isArray": "$product_ids"},
                                    "$product_ids",
                                    [],
                                ]
                            },
                            [
                                {
                                    "$cond": [
                                        {"$eq": [{"$type": "$product_id"}, "string"]},
                                        "$product_id",
                                        None,
                                    ]
                                }
                            ],
                        ]
                    }
                }
            },
            {"$unwind": "$linked_product_ids"},
            {"$match": {"linked_product_ids": {"$type": "string"}}},
            {"$group": {"_id": "$linked_product_ids"}},
            {"$project": {"_id": 0, "product_id": "$_id"}},
        ]
        product_ids_data: list[dict[str, Any]] = await db.documents.aggregate(pipeline).to_list(
            length=None
        )
        product_ids = [item["product_id"] for item in product_ids_data]

        if not product_ids:
            return []

        # Fetch products with those IDs
        products_data: list[dict[str, Any]] = await db.products.find(
            {"id": {"$in": product_ids}}
        ).to_list(length=None)
        return [Product(**product_data) for product_data in products_data]

    async def find_paginated(
        self,
        db: AgnosticDatabase,
        *,
        skip: int,
        limit: int,
        search: str = "",
    ) -> tuple[list[Product], int]:
        """Get a paginated list of products with optional name/description/category/domain search.

        Args:
            db: Database instance
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            search: Case-insensitive search string matched against name, description,
                categories, and domains

        Returns:
            Tuple of (products, total_count)
        """
        query: dict[str, Any] = {}
        if search:
            # Escape so user input is matched literally — raw regex metacharacters
            # would 500 on invalid patterns or open a ReDoS vector.
            escaped_search = re.escape(search)
            # Stored domains are bare hosts (e.g. "anthropic.com"), but users often
            # paste a full URL. Strip scheme/www and any path so "https://www.anthropic.com/"
            # still matches. Fall back to the raw term if normalization empties it
            # (e.g. the user typed only "https://") so we don't match every product.
            normalized_domain = re.sub(
                r"^(https?://)?(www\.)?", "", search.strip(), flags=re.IGNORECASE
            ).split("/")[0]
            domain_search = re.escape(normalized_domain) or escaped_search
            query = {
                "$or": [
                    {"name": {"$regex": escaped_search, "$options": "i"}},
                    {"description": {"$regex": escaped_search, "$options": "i"}},
                    {"categories": {"$regex": escaped_search, "$options": "i"}},
                    {"domains": {"$regex": domain_search, "$options": "i"}},
                ]
            }
            total, items_data = await asyncio.gather(
                db.products.count_documents(query),
                db.products.find(query)
                .sort("name", 1)
                .skip(skip)
                .limit(limit)
                .to_list(length=limit),
            )
        else:
            # No filter: estimated_document_count() is an O(1) metadata read,
            # whereas count_documents({}) scans the whole collection.
            total, items_data = await asyncio.gather(
                db.products.estimated_document_count(),
                db.products.find().sort("name", 1).skip(skip).limit(limit).to_list(length=limit),
            )
        return [Product(**item) for item in items_data], total

    # ============================================================================
    # Product Overview Storage Operations
    # ============================================================================

    async def list_analyzed_overviews(self, db: AgnosticDatabase) -> list[dict[str, Any]]:
        return await ProductIntelligenceRepository().list_sitemap_entries(db)

    async def count_products_with_overview(self, db: AgnosticDatabase) -> int:
        return await ProductIntelligenceRepository().count_with_overview(db)

    async def get_product_overview(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        intelligence = await ProductIntelligenceRepository().get_by_slug(db, product_slug)
        if not intelligence or not intelligence.overview:
            return None
        overview_data = intelligence.overview.model_dump(mode="json")
        overview_data["product_slug"] = product_slug
        overview_data["product_id"] = intelligence.product_id
        if intelligence.overview_generated_at:
            overview_data["updated_at"] = intelligence.overview_generated_at
        return {"overview": overview_data}

    async def save_product_overview(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        meta_summary: MetaSummary,
        job_id: str | None = None,
        product_id: str | None = None,
    ) -> None:
        if product_id is None:
            product = await self.find_by_slug(db, product_slug)
            if not product:
                raise ValueError(f"Product not found for slug {product_slug}")
            product_id = product.id
        await ProductIntelligenceService().save_overview(
            db,
            product_id=product_id,
            product_slug=product_slug,
            meta_summary=meta_summary,
            job_id=job_id,
        )
        logger.info("Saved product overview for %s", product_slug)

    async def delete_product_overview(self, db: AgnosticDatabase, product_slug: str) -> None:
        intelligence = await ProductIntelligenceRepository().get_by_slug(db, product_slug)
        if not intelligence:
            return
        intelligence.overview = None
        await ProductIntelligenceRepository().upsert(db, intelligence)
        logger.debug("Deleted product overview for %s", product_slug)

    # ============================================================================
    # Consumer Explainer Storage (product-level roll-up, consumer-facing)
    # ============================================================================

    async def get_product_explainer(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        intelligence = await ProductIntelligenceRepository().get_by_slug(db, product_slug)
        if not intelligence or not intelligence.explainer:
            return None
        data = intelligence.explainer.model_dump(mode="json")
        data["product_slug"] = product_slug
        return data

    async def save_product_explainer(
        self, db: AgnosticDatabase, product_slug: str, explainer: ConsumerExplainer
    ) -> bool:
        product = await self.find_by_slug(db, product_slug)
        if not product:
            return False
        return await ProductIntelligenceService().save_explainer(
            db,
            product_id=product.id,
            product_slug=product_slug,
            explainer=explainer,
        )

    async def update_product_explainer_grade(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        grade: str,
        *,
        grade_reason: str | None = None,
    ) -> None:
        intelligence = await ProductIntelligenceRepository().get_by_slug(db, product_slug)
        if not intelligence or not intelligence.explainer:
            return
        intelligence.explainer.grade = grade
        if grade_reason is not None:
            intelligence.explainer.grade_reason = grade_reason
        intelligence.updated_at = datetime.now()
        await ProductIntelligenceRepository().upsert(db, intelligence)

    async def get_product_compliance(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        intelligence = await ProductIntelligenceRepository().get_by_slug(db, product_slug)
        if not intelligence or not intelligence.compliance:
            return None
        return {
            regime: bd.model_dump(mode="json") for regime, bd in intelligence.compliance.items()
        }

    async def save_product_compliance(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        compliance: dict[str, ComplianceBreakdown],
    ) -> bool:
        product = await self.find_by_slug(db, product_slug)
        if not product:
            return False
        return await ProductIntelligenceService().save_compliance(
            db,
            product_id=product.id,
            product_slug=product_slug,
            compliance=compliance,
        )

    async def get_deep_analysis(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        intelligence = await ProductIntelligenceRepository().get_by_slug(db, product_slug)
        if not intelligence or not intelligence.deep_analysis:
            return None
        stored = intelligence.deep_analysis.model_dump(mode="json")
        stored["product_slug"] = product_slug
        return {
            "deep_analysis": stored,
            "document_signature": intelligence.deep_analysis_document_signature,
        }

    async def save_deep_analysis(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        deep_analysis: ProductDeepAnalysis,
        document_signature: str,
    ) -> None:
        product = await self.find_by_slug(db, product_slug)
        if not product:
            raise ValueError(f"Product not found for slug {product_slug}")
        await ProductIntelligenceService().save_deep_analysis(
            db,
            product_id=product.id,
            product_slug=product_slug,
            deep_analysis=deep_analysis,
            document_signature=document_signature,
        )
        logger.debug(
            "Saved deep analysis for %s with signature %s...",
            product_slug,
            document_signature[:16],
        )

    # ============================================================================
    # Document Statistics
    # ============================================================================

    async def get_document_counts(
        self, db: AgnosticDatabase, product_id: str
    ) -> dict[str, int] | None:
        """Get document counts for a product.

        Args:
            db: Database instance
            product_id: Product ID

        Returns:
            Dictionary with total, analyzed, and pending counts, or None on error
        """
        try:
            membership = _product_document_membership_query(product_id)
            total = await db.documents.count_documents(membership)
            analyzed = await db.documents.count_documents(
                {"$and": [membership, {"analysis": {"$exists": True, "$ne": None}}]}
            )
            pending = max(0, total - analyzed)
            return {
                "total": int(total),
                "analyzed": int(analyzed),
                "pending": int(pending),
            }
        except Exception:
            return None

    async def get_document_types(
        self, db: AgnosticDatabase, product_id: str
    ) -> dict[str, int] | None:
        """Get document type counts for a product.

        Args:
            db: Database instance
            product_id: Product ID

        Returns:
            Dictionary mapping document types to counts, or None on error
        """
        try:
            pipeline = [
                {"$match": _product_document_membership_query(product_id)},
                {"$group": {"_id": "$doc_type", "count": {"$sum": 1}}},
            ]
            agg: list[dict[str, Any]] = await db.documents.aggregate(pipeline).to_list(length=None)
            return {item["_id"]: int(item["count"]) for item in agg} if agg else None
        except Exception:
            return None
