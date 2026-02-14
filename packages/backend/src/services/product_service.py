"""Product service for business logic operations.

This service coordinates business logic and delegates data access
to the ProductRepository. It no longer owns database connections
and instead accepts database instances as parameters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import (
    DocumentSummary,
    MetaSummary,
    ProductAnalysis,
    ProductDeepAnalysis,
    ProductOverview,
)
from src.models.product import Product
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
    ) -> None:
        """Save the product overview payload to the database.

        Args:
            db: Database instance
            product_slug: Product slug
            meta_summary: Overview payload (MetaSummary shape)
        """
        await self._product_repo.save_product_overview(db, product_slug, meta_summary)

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

    async def get_product_overview(self, db: AgnosticDatabase, slug: str) -> ProductOverview | None:
        """Get the Level 1 overview for a product.

        This is business logic that transforms cached data into a user-facing overview.

        Args:
            db: Database instance
            slug: Product slug

        Returns:
            ProductOverview or None if not available
        """
        overview_data = await self._product_repo.get_product_overview(db, slug)
        if not overview_data:
            return None
        meta_summary = MetaSummary(**overview_data["overview"])

        # Fetch product info (name, id)
        product = await self._product_repo.find_by_slug(db, slug)

        # Compute document counts and types
        document_counts = None
        document_types = None
        if product:
            document_counts = await self._product_repo.get_document_counts(db, product.id)
            document_types = await self._product_repo.get_document_types(db, product.id)

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
        overview.keypoints = getattr(meta_summary, "keypoints", None)
        overview.document_counts = document_counts
        overview.document_types = document_types

        # Attach new structured fields for Overview redesign
        overview.data_collection_details = getattr(meta_summary, "data_collection_details", None)
        overview.third_party_details = getattr(meta_summary, "third_party_details", None)

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
            docs = await self._document_repo.find_by_product_id(db, product.id)
            documents = [DocumentSummary.from_document(doc) for doc in docs]

        return ProductAnalysis(
            overview=overview,
            detailed_scores=meta_summary.scores,
            compliance=None,  # TODO: Store compliance in DB or calculate it
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

        docs = await self._document_repo.find_by_product_id(db, product.id)
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
            risk_score=meta.risk_score,
            one_line_summary=meta.summary,
            data_collected=meta.data_collected,
            data_purposes=meta.data_purposes,
            your_rights=meta.your_rights,
            dangers=meta.dangers,
            benefits=meta.benefits,
            recommended_actions=meta.recommended_actions,
        )
