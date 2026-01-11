"""Product repository for data access operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import MetaSummary, ProductDeepAnalysis
from src.models.product import Product
from src.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


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
        # Use aggregation to find distinct product_ids from documents
        pipeline = [
            {"$group": {"_id": "$product_id"}},
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

    # ============================================================================
    # Product Overview Storage Operations
    # ============================================================================

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
    ) -> None:
        """Save the product overview payload to the database.

        Args:
            db: Database instance
            product_slug: Product slug
            meta_summary: Overview payload (MetaSummary shape)
        """
        summary_data = meta_summary.model_dump()
        summary_data["product_slug"] = product_slug
        summary_data["updated_at"] = datetime.now().isoformat()

        await db.product_overviews.update_one(
            {"product_slug": product_slug},
            {"$set": summary_data},
            upsert=True,
        )
        logger.debug(f"Saved product overview for {product_slug}")

    async def delete_product_overview(self, db: AgnosticDatabase, product_slug: str) -> None:
        """Delete the stored product overview for a product.

        Args:
            db: Database instance
            product_slug: Product slug
        """
        await db.product_overviews.delete_one({"product_slug": product_slug})
        logger.debug(f"Deleted product overview for {product_slug}")

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
        analysis_data["updated_at"] = datetime.now().isoformat()

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
            total = await db.documents.count_documents({"product_id": product_id})
            analyzed = await db.documents.count_documents(
                {"product_id": product_id, "analysis": {"$exists": True}}
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
                {"$match": {"product_id": product_id}},
                {"$group": {"_id": "$doc_type", "count": {"$sum": 1}}},
            ]
            agg: list[dict[str, Any]] = await db.documents.aggregate(pipeline).to_list(length=None)
            return {item["_id"]: int(item["count"]) for item in agg} if agg else None
        except Exception:
            return None
