"""Document repository for data access operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import Document, DocumentAnalysis
from src.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


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

        document["analysis"] = analysis

    return document


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

    async def find_by_product_id(self, db: AgnosticDatabase, product_id: str) -> list[Document]:
        """Get all documents for a specific product.

        Args:
            db: Database instance
            product_id: Product ID

        Returns:
            List of documents for the product
        """
        documents: list[dict[str, Any]] = await db.documents.find(
            {"product_id": product_id}
        ).to_list(length=None)
        return [Document(**_normalize_document_record(document)) for document in documents]

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
        self, db: AgnosticDatabase, product_slug: str | None = None
    ) -> list[Document]:
        """Get documents that have analysis data.

        Args:
            db: Database instance
            product_slug: Optional product slug to filter by

        Returns:
            List of documents with analysis
        """
        query: dict[str, Any] = {"analysis": {"$exists": True, "$ne": None}}
        if product_slug:
            query["product_slug"] = product_slug

        documents: list[dict[str, Any]] = await db.documents.find(query).to_list(length=None)
        return [Document(**_normalize_document_record(document)) for document in documents]

    # ============================================================================
    # Document Persistence Operations
    # ============================================================================

    async def save(self, db: AgnosticDatabase, document: Document) -> Document:
        """Store a document in the database.

        Args:
            db: Database instance
            document: Document to store

        Returns:
            The stored document

        Raises:
            Exception: If storage fails
        """
        try:
            document_dict = document.model_dump()
            await db.documents.insert_one(document_dict)
            logger.info(f"Stored document {document.id} for product {document.product_id}")
            return document
        except Exception as e:
            logger.error(f"Error storing document {document.id}: {e}")
            raise e

    async def update(self, db: AgnosticDatabase, document: Document) -> bool:
        """Update a document in the database.

        Args:
            db: Database instance
            document: Document to update

        Returns:
            True if document was updated, False otherwise

        Raises:
            Exception: If update fails
        """
        try:
            result = await db.documents.update_one(
                {"id": document.id}, {"$set": document.model_dump()}
            )
            success = result.modified_count > 0
            if not success:
                logger.warning(f"No document found with id {document.id} to update")
            return bool(success)
        except Exception as e:
            logger.error(f"Error updating document {document.id}: {e}")
            raise e

    async def delete(self, db: AgnosticDatabase, document_id: str) -> bool:
        """Delete a document from the database.

        Args:
            db: Database instance
            document_id: ID of document to delete

        Returns:
            True if document was deleted, False otherwise

        Raises:
            Exception: If deletion fails
        """
        try:
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
            success = result.modified_count > 0
            if success:
                logger.info(f"Updated analysis for document {document_id}")
            return bool(success)
        except Exception as e:
            logger.error(f"Error updating analysis for document {document_id}: {e}")
            raise e
