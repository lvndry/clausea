from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import shortuuid
from langchain_text_splitters import RecursiveCharacterTextSplitter
from motor.core import AgnosticDatabase

from src.core.config import config
from src.core.logging import get_logger
from src.embedding import embed_product_documents
from src.llm import get_embeddings
from src.models.document import Document
from src.pinecone_client import INDEX_NAME, pc
from src.repositories.document_repository import DocumentRepository
from src.repositories.product_repository import ProductRepository
from src.services.document_service import DocumentService
from src.services.product_service import ProductService

logger = get_logger(__name__)


def _log_document_size_info(document: Document) -> None:
    """
    Log document size information for monitoring and debugging.

    Args:
        document: The document to analyze
    """
    text_bytes = len(document.text.encode("utf-8"))
    text_mb = text_bytes / (1024 * 1024)

    if text_mb > 4.0:
        logger.warning(
            f"Large document detected: {document.id} ({text_mb:.2f}MB) - will be truncated"
        )
    elif text_mb > 1.0:
        logger.info(f"Medium document: {document.id} ({text_mb:.2f}MB)")
    else:
        logger.debug(f"Small document: {document.id} ({text_mb:.2f}MB)")

    # Log chunk count estimate
    estimated_chunks = (
        len(document.text) // config.embedding.chunk_size
    )  # Approximate based on chunk size
    logger.debug(f"Estimated chunks for {document.id}: ~{estimated_chunks}")


def _compute_chunk_offsets(full_text: str, chunks: list[str]) -> list[tuple[int, int]]:
    """Compute start/end offsets for each chunk within the full_text by sequential search."""
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for chunk in chunks:
        start = full_text.find(chunk, cursor)
        if start == -1:
            # Fallback: search from beginning if not found after cursor
            start = full_text.find(chunk)
        end = start + len(chunk) if start != -1 else -1
        offsets.append((max(start, 0), max(end, 0)))
        if start != -1:
            cursor = end
    return offsets


def _create_product_service() -> ProductService:
    """Create ProductService without relying on service factory to avoid cycles."""
    product_repo = ProductRepository()
    document_repo = DocumentRepository()
    return ProductService(product_repo, document_repo)


def _create_document_service() -> DocumentService:
    """Create DocumentService without relying on service factory to avoid cycles."""
    document_repo = DocumentRepository()
    product_repo = ProductRepository()
    return DocumentService(document_repo, product_repo)


class EmbeddingService:
    """Service for handling document embedding operations without UI dependencies.

    This module exposes async methods only. Any threading, warning suppression,
    or UI-specific concerns must be handled in the caller (e.g., dashboard layer).
    """

    async def embed_single_product(self, db: AgnosticDatabase, product_slug: str) -> bool:
        """Embed documents for a single product.

        Args:
            db: Database instance
            product_slug: The slug of the product to embed

        Returns:
            True if successful, False if failed
        """
        try:
            product_service = _create_product_service()
            document_service = _create_document_service()

            product = await product_service.get_product_by_slug(db, product_slug)
            if not product:
                logger.error(f"Product {product_slug} not found for embedding")
                return False

            await embed_product_documents(product.id, document_service, db, namespace=product_slug)
            return True
        except Exception as e:
            logger.error(f"Error embedding {product_slug}: {str(e)}", exc_info=True)
            return False

    async def embed_multiple_products(
        self, db: AgnosticDatabase, product_slugs: Iterable[str], max_concurrency: int = 3
    ) -> list[tuple[str, bool]]:
        """Embed documents for multiple products concurrently using asyncio.

        Args:
            db: Database instance
            product_slugs: Iterable of product slugs to embed
            max_concurrency: Maximum number of concurrent embedding tasks

        Returns:
            List of tuples (product_slug, success_status)
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded_embed(slug: str) -> tuple[str, bool]:
            async with semaphore:
                success = await self.embed_single_product(db, slug)
                return slug, success

        tasks = [_bounded_embed(slug) for slug in product_slugs]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    async def embed_document(self, document: Document, namespace: str) -> None:
        """Embed a single document into the specified namespace."""
        index = pc.Index(INDEX_NAME)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.embedding.chunk_size,
            chunk_overlap=config.embedding.chunk_overlap,
            separators=["\n\n", "\n", ".", ";"],
        )

        # Log document size information
        _log_document_size_info(document)

        chunks = splitter.split_text(document.text)
        offsets = _compute_chunk_offsets(document.text, chunks)

        all_vectors: list[dict[str, Any]] = []

        # Process chunks in batches
        batch_size = config.embedding.batch_size
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_offsets = offsets[i : i + batch_size]

            try:
                chunk_embeddings = await get_embeddings(
                    input=batch_chunks,
                    input_type="document",
                )

                logger.info(f"Embedding batch {i // batch_size + 1}: {len(batch_chunks)} chunks")

                # Create vectors for each chunk in this batch
                for idx, (chunk, embedding_data) in enumerate(
                    zip(batch_chunks, chunk_embeddings.data, strict=False)
                ):
                    offset_idx = i + idx
                    start, end = batch_offsets[idx] if idx < len(batch_offsets) else (0, 0)
                    all_vectors.append(
                        {
                            "id": shortuuid.uuid(),
                            "values": embedding_data["embedding"],
                            "metadata": {
                                "document_id": document.id,
                                "title": document.title,
                                "document_type": document.doc_type,
                                "url": document.url,
                                "locale": document.locale,
                                "chunk_text": chunk,
                                "chunk_start": start,
                                "chunk_end": end,
                                "chunk_index": offset_idx,
                                "effective_date": document.effective_date.isoformat()
                                if document.effective_date
                                else "",
                            },
                        }
                    )

            except Exception as e:
                logger.error(
                    f"Error embedding batch {i // batch_size + 1} for document {document.id}: {e}"
                )
                # Continue with next batch instead of failing completely
                continue

        if all_vectors:
            # Upsert vectors in batches
            batch_size = config.embedding.upsert_batch_size
            for i in range(0, len(all_vectors), batch_size):
                batch = all_vectors[i : i + batch_size]
                index.upsert(vectors=batch, namespace=namespace)
                logger.info(
                    f"Upserted batch {i // batch_size + 1} ({len(batch)} vectors) to Pinecone namespace '{namespace}' for document {document.id}"
                )

            logger.info(
                "Successfully upserted %d total vectors to Pinecone namespace '%s' for document %s",
                len(all_vectors),
                namespace,
                document.id,
            )
        else:
            logger.warning(
                "No vectors created for uploaded document to Pinecone namespace '%s' for document %s",
                namespace,
                document.id,
            )
