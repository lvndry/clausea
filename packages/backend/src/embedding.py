from typing import Any

import shortuuid
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.config import config
from src.core.logging import get_logger
from src.llm import get_embeddings
from src.models.document import Document
from src.pinecone_client import INDEX_NAME, init_pinecone_index, pc

load_dotenv()
logger = get_logger(__name__)


VOYAGE_LAW_2_DIMENSION = 1024
init_pinecone_index(VOYAGE_LAW_2_DIMENSION)


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


async def embed_product_documents(
    product_id: str,
    document_service: Any,
    db: Any,
    namespace: str | None = None,
) -> None:
    """
    Process documents by splitting their markdown content and creating embeddings for each chunk.

    Args:
        product_id: The id of the product
        document_service: DocumentService instance
        db: Database instance
        namespace: The namespace to use for the embeddings
    """
    documents = await document_service.get_product_documents(db, product_id)
    logger.info(f"Embedding {len(documents)} documents for product {product_id}")

    index = pc.Index(INDEX_NAME)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.embedding.chunk_size,
        chunk_overlap=config.embedding.chunk_overlap,
        separators=["\n\n", "\n", ".", ";"],
    )
    all_vectors: list[dict[str, Any]] = []

    for doc in documents:
        # Log document size information
        _log_document_size_info(doc)

        chunks = splitter.split_text(doc.text)
        offsets = _compute_chunk_offsets(doc.text, chunks)
        logger.debug(f"Split into {len(chunks)} chunks")

        # Process chunks in batches to avoid overwhelming the embedding service
        batch_size = config.embedding.batch_size
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_offsets = offsets[i : i + batch_size]

            try:
                chunk_embeddings = await get_embeddings(
                    input=batch_chunks,
                    input_type="document",
                )

                # Safely extract token count; chunk_embeddings.usage may be None
                usage = getattr(chunk_embeddings, "usage", None)
                token_count = getattr(usage, "total_tokens", "unknown")

                logger.info(
                    f"Embedding batch {i // batch_size + 1}: {len(batch_chunks)} chunks, {token_count} tokens"
                )

                # Create vectors for each chunk in this batch
                for idx, (chunk, embedding_data) in enumerate(
                    zip(batch_chunks, chunk_embeddings.data, strict=False)
                ):
                    offset_idx = i + idx
                    start, end = batch_offsets[idx] if idx < len(batch_offsets) else (0, 0)
                    vector = {
                        "id": shortuuid.uuid(),
                        "values": embedding_data["embedding"],
                        "metadata": {
                            "document_id": doc.id,
                            "title": doc.title,
                            "document_type": doc.doc_type,
                            "url": doc.url,
                            "locale": doc.locale,
                            "chunk_text": chunk,
                            "chunk_start": start,
                            "chunk_end": end,
                            "chunk_index": offset_idx,
                            "effective_date": doc.effective_date.isoformat()
                            if doc.effective_date
                            else "",
                        },
                    }
                    all_vectors.append(vector)

            except Exception as e:
                logger.error(
                    f"Error embedding batch {i // batch_size + 1} for document {doc.id}: {e}"
                )
                # Continue with next batch instead of failing completely
                continue

        logger.info(f"Processed {len(chunks)} chunks for document {doc.url}")

    if all_vectors:
        # Upsert vectors in batches to avoid overwhelming Pinecone
        batch_size = config.embedding.upsert_batch_size
        for i in range(0, len(all_vectors), batch_size):
            batch = all_vectors[i : i + batch_size]
            index.upsert(vectors=batch, namespace=namespace)
            logger.info(
                f"Upserted batch {i // batch_size + 1} ({len(batch)} vectors) to Pinecone namespace '{namespace}'"
            )

        logger.info(
            f"Successfully upserted {len(all_vectors)} total vectors to Pinecone namespace '{namespace}'"
        )
    else:
        logger.warning("No vectors were created to upsert to Pinecone namespace '%s'", namespace)


async def embed_document(document: Document, namespace: str) -> None:
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
