from __future__ import annotations

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import Document
from src.models.document_change import DocumentChange
from src.repositories.document_change_repository import DocumentChangeRepository

logger = get_logger(__name__)


class DocumentVersionRepository:
    """Records slim document change events (replaces full markdown archiving)."""

    async def archive(
        self,
        db: AgnosticDatabase,
        existing_doc: Document,
        job_id: str | None,
        changed_fields: list[str],
        *,
        previous_hash: str | None = None,
    ) -> None:
        product_slug: str | None = None
        if existing_doc.product_id:
            product = await db.products.find_one({"id": existing_doc.product_id}, {"slug": 1})
            if product:
                product_slug = product.get("slug")

        if not existing_doc.content_hash:
            logger.debug(
                "Skipping document change record — no content_hash on %s", existing_doc.url
            )
            return

        change = DocumentChange(
            document_id=existing_doc.id,
            product_id=existing_doc.product_id,
            product_slug=product_slug,
            content_hash=existing_doc.content_hash,
            previous_hash=previous_hash,
            changed_fields=changed_fields,
            job_id=job_id,
        )
        await DocumentChangeRepository().record(db, change)
        logger.debug(
            "Recorded document change for %s (changed: %s)", existing_doc.url, changed_fields
        )
