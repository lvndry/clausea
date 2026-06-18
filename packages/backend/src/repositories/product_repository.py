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
from src.repositories.product_overview_history_repository import ProductOverviewHistoryRepository

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
        return [Product(**p) for p in items_data], total

    # ============================================================================
    # Product Overview Storage Operations
    # ============================================================================

    async def list_analyzed_overviews(self, db: AgnosticDatabase) -> list[dict[str, Any]]:
        """Slug + last-updated for every product that has a completed overview.

        Used to build the sitemap: only analyzed products carry real content worth
        indexing (the rest render an 'indexation in progress' placeholder).
        """
        cursor = db.product_overviews.find({}, {"_id": 0, "product_slug": 1, "updated_at": 1})
        return await cursor.to_list(length=None)

    async def count_product_overviews(self, db: AgnosticDatabase) -> int:
        """Count products that have a completed analysis (a stored overview).

        Uses estimated_document_count() — an O(1) metadata read — since this counts
        the whole collection with no filter (consistent with get_products_paginated).
        """
        return await db.product_overviews.estimated_document_count()

    async def get_product_overview(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        """Get the stored product overview data for a product.

        Args:
            db: Database instance
            product_slug: Product slug

        Returns:
            Dictionary with 'overview' key, or None
        """
        stored_data = await db.product_overviews.find_one({"product_slug": product_slug})
        return {"overview": stored_data} if stored_data else None

    async def save_product_overview(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        meta_summary: MetaSummary,
        job_id: str | None = None,
    ) -> None:
        """Save the product overview payload to the database.

        Args:
            db: Database instance
            product_slug: Product slug
            meta_summary: Overview payload (MetaSummary shape)
            job_id: Optional pipeline job that produced this overview
        """
        summary_data = meta_summary.model_dump()
        summary_data["product_slug"] = product_slug
        summary_data["updated_at"] = datetime.now()

        existing = await db.product_overviews.find_one({"product_slug": product_slug})
        await ProductOverviewHistoryRepository().save_snapshot(
            db,
            product_slug=product_slug,
            overview_data=summary_data,
            prev_overview_data=existing,
            job_id=job_id,
        )

        result = await db.product_overviews.update_one(
            {"product_slug": product_slug},
            {"$set": summary_data},
            upsert=True,
        )
        logger.info(
            "Saved product overview for %s (matched=%s modified=%s upserted_id=%s)",
            product_slug,
            result.matched_count,
            result.modified_count,
            getattr(result, "upserted_id", None),
        )

    async def delete_product_overview(self, db: AgnosticDatabase, product_slug: str) -> None:
        """Delete the stored product overview for a product.

        Args:
            db: Database instance
            product_slug: Product slug
        """
        await db.product_overviews.delete_one({"product_slug": product_slug})
        logger.debug(f"Deleted product overview for {product_slug}")

    # ============================================================================
    # Consumer Explainer Storage (product-level roll-up, consumer-facing)
    # ============================================================================

    async def get_product_explainer(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        """Get the stored product-level consumer explainer, or None."""
        return await db.product_explainers.find_one({"product_slug": product_slug}, {"_id": 0})

    async def save_product_explainer(
        self, db: AgnosticDatabase, product_slug: str, explainer: ConsumerExplainer
    ) -> bool:
        """Upsert the product-level consumer explainer. Returns True when it landed."""
        data = explainer.model_dump()
        data["product_slug"] = product_slug
        data["updated_at"] = datetime.now()
        result = await db.product_explainers.update_one(
            {"product_slug": product_slug}, {"$set": data}, upsert=True
        )
        return result.matched_count > 0 or result.upserted_id is not None

    async def update_product_explainer_grade(
        self, db: AgnosticDatabase, product_slug: str, grade: str
    ) -> None:
        """Update only the stored explainer grade for a product.

        Used by the service layer when reconciling legacy explainer rows against
        the canonical overview score, without rewriting the entire explainer.
        """
        await db.product_explainers.update_one(
            {"product_slug": product_slug},
            {"$set": {"grade": grade, "updated_at": datetime.now()}},
        )

    # ============================================================================
    # Compliance Assessment Storage (product-level, per-regime score + why)
    # ============================================================================

    async def get_product_compliance(
        self, db: AgnosticDatabase, product_slug: str
    ) -> dict[str, Any] | None:
        """Get the stored per-regime compliance breakdown ({regime: {...}}), or None."""
        stored = await db.product_compliance.find_one({"product_slug": product_slug})
        return stored.get("compliance") if stored else None

    async def save_product_compliance(
        self,
        db: AgnosticDatabase,
        product_slug: str,
        compliance: dict[str, ComplianceBreakdown],
    ) -> bool:
        """Upsert the per-regime compliance breakdown. Returns True when it landed."""
        data = {
            "product_slug": product_slug,
            "compliance": {regime: bd.model_dump() for regime, bd in compliance.items()},
            "updated_at": datetime.now(),
        }
        result = await db.product_compliance.update_one(
            {"product_slug": product_slug}, {"$set": data}, upsert=True
        )
        return result.matched_count > 0 or result.upserted_id is not None

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
        stored_data = await db.deep_analyses.find_one({"product_slug": product_slug})
        if not stored_data:
            return None

        return {
            "deep_analysis": stored_data,
            "document_signature": stored_data.get("document_signature"),
        }

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
        analysis_data = deep_analysis.model_dump()
        analysis_data["product_slug"] = product_slug
        analysis_data["document_signature"] = document_signature
        analysis_data["updated_at"] = datetime.now()

        await db.deep_analyses.update_one(
            {"product_slug": product_slug},
            {"$set": analysis_data},
            upsert=True,
        )
        logger.debug(
            f"Saved deep analysis for {product_slug} with signature {document_signature[:16]}..."
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
