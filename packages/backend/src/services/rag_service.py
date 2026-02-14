"""RAG service for managing RAG operations.

This service is stateless and doesn't need database access or repository.
It's a pure wrapper around the RAG module.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import get_logger
from src.rag import get_answer

logger = get_logger(__name__)


class RAGService:
    """Service for RAG-related operations.

    This is a stateless service that doesn't need database access.
    """

    async def get_answer(
        self, question: str, product_slug: str, namespace: str | None = None
    ) -> str:
        """Get an answer using RAG.

        Args:
            question: User's question
            product_slug: Product slug for context
            namespace: Optional namespace for vector search

        Returns:
            AI-generated answer
        """
        try:
            answer = await get_answer(question, product_slug, namespace=namespace)
            logger.info(f"Generated RAG answer for product {product_slug}")
            return str(answer)
        except Exception as e:
            logger.error(f"Error getting RAG answer for product {product_slug}: {e}")
            raise e

    def get_product_context(self, product_slug: str) -> dict[str, Any]:
        """Get context information for a product.

        Args:
            product_slug: Product slug

        Returns:
            Context dictionary
        """
        try:
            # This could be expanded to include more context gathering
            context = {
                "product_slug": product_slug,
                "namespace": product_slug.lower().replace(" ", "_"),
            }
            return context
        except Exception as e:
            logger.error(f"Error getting context for product {product_slug}: {e}")
            raise e
