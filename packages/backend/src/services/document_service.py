"""Document service for business logic operations.

This service coordinates business logic and delegates data access
to repositories. It no longer owns database connections and instead
accepts database instances as parameters.
"""

from __future__ import annotations

from datetime import datetime

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import (
    CORE_DOC_TYPES,
    ConsumerExplainer,
    Document,
    DocumentAnalysis,
)
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_repository import ProductRepository

logger = get_logger(__name__)


class DocumentService:
    """Service for document-related business logic.

    This service coordinates business logic and uses repositories for
    data access. It doesn't own database connections - those are passed
    via parameters from the context manager.
    """

    def __init__(
        self,
        document_repo: DocumentRepository,
        product_repo: ProductRepository,
    ) -> None:
        """Initialize DocumentService with repository dependencies.

        Args:
            document_repo: Repository for document data access
            product_repo: Repository for product data access (for cache invalidation)
        """
        self._document_repo = document_repo
        self._product_repo = product_repo

    @staticmethod
    def _assign_tier_relevance(document: Document) -> None:
        """Classify document relevance for free/pro source access."""
        document.tier_relevance = "core" if document.doc_type in CORE_DOC_TYPES else "extended"

    # ============================================================================
    # Document Query Operations
    # ============================================================================

    async def get_document_by_id(self, db: AgnosticDatabase, document_id: str) -> Document | None:
        """Get a document by its ID.

        Args:
            db: Database instance
            document_id: Document ID

        Returns:
            Document or None if not found
        """
        return await self._document_repo.find_by_id(db, document_id)

    async def get_document_by_url(self, db: AgnosticDatabase, url: str) -> Document | None:
        """Get a document by its URL.

        Args:
            db: Database instance
            url: Document URL

        Returns:
            Document or None if not found
        """
        return await self._document_repo.find_by_url(db, url)

    async def get_product_document_by_url(
        self, db: AgnosticDatabase, product_id: str, url: str
    ) -> Document | None:
        """Get a document by URL for one product only."""
        return await self._document_repo.find_by_product_and_url(db, product_id, url)

    async def link_document_to_product(
        self, db: AgnosticDatabase, document_id: str, product_id: str
    ) -> bool:
        """Link an existing canonical document to a product."""
        return await self._document_repo.link_to_product(db, document_id, product_id)

    async def get_product_documents(self, db: AgnosticDatabase, product_id: str) -> list[Document]:
        """Get all documents for a specific product.

        Args:
            db: Database instance
            product_id: Product ID

        Returns:
            List of documents for the product
        """
        documents: list[Document] = await self._document_repo.find_by_product_id_full(
            db, product_id
        )
        return documents

    async def get_product_documents_by_slug(
        self, db: AgnosticDatabase, product_slug: str
    ) -> list[Document]:
        """Get all documents for a specific product by slug.

        Args:
            db: Database instance
            product_slug: Product slug

        Returns:
            List of documents for the product

        Raises:
            ValueError: If product not found
        """
        product = await self._product_repo.find_by_slug(db, product_slug)
        if not product:
            raise ValueError(f"Product with slug {product_slug} not found")
        documents: list[Document] = await self._document_repo.find_by_product_id_full(
            db, product.id
        )
        return documents

    async def get_documents_with_analysis(
        self, db: AgnosticDatabase, product_id: str | None = None
    ) -> list[Document]:
        """Get documents that have analysis data.

        Args:
            db: Database instance
            product_id: Optional product ID to filter by

        Returns:
            List of documents with analysis
        """
        documents: list[Document] = await self._document_repo.find_with_analysis(db, product_id)
        return documents

    async def get_recent_document_urls(
        self, db: AgnosticDatabase, product_id: str, cutoff: datetime
    ) -> list[str]:
        """Return URLs of a product's documents written at or after ``cutoff``.

        Used by the pipeline to tell the crawler which freshly stored docs to skip
        re-fetching when resuming a retried crawl.
        """
        urls: list[str] = await self._document_repo.find_recent_urls_by_product(
            db, product_id, cutoff
        )
        return urls

    # ============================================================================
    # Document Persistence Operations (with cache invalidation)
    # ============================================================================

    async def store_document(self, db: AgnosticDatabase, document: Document) -> Document:
        """Store a document in the database.

        Includes business logic: invalidates product meta-summary cache.

        Args:
            db: Database instance
            document: Document to store

        Returns:
            The stored document

        Raises:
            Exception: If storage fails
        """
        try:
            self._assign_tier_relevance(document)
            # Stamp the write time so a retried crawl can recognise freshly stored
            # docs and skip re-fetching them (see Document.updated_at).
            document.updated_at = datetime.now()
            result = await self._document_repo.save(db, document)

            return result
        except Exception as e:
            logger.error(f"Error storing document {document.id}: {e}")
            raise e

    async def update_document(
        self,
        db: AgnosticDatabase,
        document: Document,
        *,
        invalidate_product_overview: bool = False,
    ) -> bool:
        """Update a document in the database.

        When ``invalidate_product_overview`` is True (default), deletes the cached
        product overview for this product so readers do not see a stale meta-summary.

        Batch analysers (e.g. ``analyse_product_documents``) should pass ``False`` so each
        document save does not wipe the overview row; the pipeline then replaces it in
        ``generate_product_overview``. Otherwise a later partial re-run can leave
        ``product_overviews`` empty forever if overview generation does not run again.

        Args:
            db: Database instance
            document: Document to update
            invalidate_product_overview: If True, delete stored product overview for this product

        Returns:
            True if document was updated, False otherwise

        Raises:
            Exception: If update fails
        """
        try:
            self._assign_tier_relevance(document)
            document.updated_at = datetime.now()
            success = await self._document_repo.update(db, document)

            if success and invalidate_product_overview:
                # Business logic: Invalidate product overview cache for this product
                try:
                    product = await self._product_repo.find_by_id(db, document.product_id)
                    if product:
                        await self._product_repo.delete_product_overview(db, product.slug)
                        logger.debug(f"Deleted product overview for product {product.slug}")
                except Exception as cache_error:
                    # Don't fail document update if cache invalidation fails
                    logger.warning(
                        f"Failed to invalidate cache for document {document.id}: {cache_error}"
                    )

            return bool(success)
        except Exception as e:
            logger.error(f"Error updating document {document.id}: {e}")
            raise e

    async def delete_document(self, db: AgnosticDatabase, document_id: str) -> bool:
        """Delete a document from the database.

        Includes business logic: invalidates product meta-summary cache.

        Args:
            db: Database instance
            document_id: ID of document to delete

        Returns:
            True if document was deleted, False otherwise

        Raises:
            Exception: If deletion fails
        """
        try:
            # Get document first to get product_id for cache invalidation
            document = await self._document_repo.find_by_id(db, document_id)
            product_id = document.product_id if document else None

            success = await self._document_repo.delete(db, document_id)

            if success and product_id:
                # Business logic: Invalidate product overview cache for this product
                try:
                    product = await self._product_repo.find_by_id(db, product_id)
                    if product:
                        await self._product_repo.delete_product_overview(db, product.slug)
                        logger.debug(f"Deleted product overview for product {product.slug}")
                except Exception as cache_error:
                    # Don't fail document deletion if cache invalidation fails
                    logger.warning(
                        f"Failed to invalidate cache for document {document_id}: {cache_error}"
                    )

            return bool(success)
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            raise e

    # ============================================================================
    # Analysis Operations
    # ============================================================================

    async def update_document_analysis(
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
        updated: bool = await self._document_repo.update_analysis(db, document_id, analysis)
        return updated

    async def update_document_consumer_explainer(
        self, db: AgnosticDatabase, document_id: str, explainer: ConsumerExplainer
    ) -> bool:
        """Persist the plain-English consumer explainer for one document.

        Args:
            db: Database instance
            document_id: Document ID
            explainer: ConsumerExplainer object (post-validation/grade-clamp)

        Returns:
            True if a document was matched and updated, False otherwise.
        """
        updated: bool = await self._document_repo.update_consumer_explainer(
            db, document_id, explainer
        )
        return updated
