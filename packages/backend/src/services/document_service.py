"""Document service for business logic operations.

This service coordinates business logic and delegates data access
to repositories. It no longer owns database connections and instead
accepts database instances as parameters.
"""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import Document, DocumentAnalysis
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

    # ============================================================================
    # Document Query Operations
    # ============================================================================

    async def get_all_documents(self, db: AgnosticDatabase) -> list[Document]:
        """Get all documents from the database.

        Args:
            db: Database instance

        Returns:
            List of all documents
        """
        documents: list[Document] = await self._document_repo.find_all(db)
        return documents

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

    async def get_product_documents(self, db: AgnosticDatabase, product_id: str) -> list[Document]:
        """Get all documents for a specific product.

        Args:
            db: Database instance
            product_id: Product ID

        Returns:
            List of documents for the product
        """
        documents: list[Document] = await self._document_repo.find_by_product_id(db, product_id)
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
        documents: list[Document] = await self._document_repo.find_by_product_id(db, product.id)
        return documents

    async def get_documents_by_type(self, db: AgnosticDatabase, doc_type: str) -> list[Document]:
        """Get all documents of a specific type.

        Args:
            db: Database instance
            doc_type: Document type

        Returns:
            List of documents of the specified type
        """
        documents: list[Document] = await self._document_repo.find_by_type(db, doc_type)
        return documents

    async def get_documents_with_analysis(
        self, db: AgnosticDatabase, product_slug: str | None = None
    ) -> list[Document]:
        """Get documents that have analysis data.

        Args:
            db: Database instance
            product_slug: Optional product slug to filter by

        Returns:
            List of documents with analysis
        """
        documents: list[Document] = await self._document_repo.find_with_analysis(db, product_slug)
        return documents

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
            result = await self._document_repo.save(db, document)

            # Business logic: Invalidate product overview cache for this product
            try:
                product = await self._product_repo.find_by_id(db, document.product_id)
                if product:
                    await self._product_repo.delete_product_overview(db, product.slug)
                    logger.debug(f"Deleted product overview for product {product.slug}")
            except Exception as cache_error:
                # Don't fail document storage if cache invalidation fails
                logger.warning(
                    f"Failed to invalidate cache for document {document.id}: {cache_error}"
                )

            return result
        except Exception as e:
            logger.error(f"Error storing document {document.id}: {e}")
            raise e

    async def update_document(self, db: AgnosticDatabase, document: Document) -> bool:
        """Update a document in the database.

        Includes business logic: invalidates product meta-summary cache.

        Args:
            db: Database instance
            document: Document to update

        Returns:
            True if document was updated, False otherwise

        Raises:
            Exception: If update fails
        """
        try:
            success = await self._document_repo.update(db, document)

            if success:
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
