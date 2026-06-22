from __future__ import annotations

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import Document
from src.models.document_version import DocumentVersion

logger = get_logger(__name__)


class DocumentVersionRepository:
    async def archive(
        self,
        db: AgnosticDatabase,
        existing_doc: Document,
        job_id: str | None,
        changed_fields: list[str],
    ) -> None:
        product_slug: str | None = None
        if existing_doc.product_id:
            product = await db.products.find_one({"id": existing_doc.product_id}, {"slug": 1})
            if product:
                product_slug = product.get("slug")

        version = DocumentVersion(
            document_id=existing_doc.id,
            product_id=existing_doc.product_id,
            url=existing_doc.url,
            title=existing_doc.title,
            doc_type=existing_doc.doc_type,
            locale=existing_doc.locale,
            regions=list(existing_doc.regions),
            effective_date=existing_doc.effective_date,
            markdown=existing_doc.markdown,
            text=existing_doc.markdown,
            content_hash=existing_doc.content_hash,
            metadata=dict(existing_doc.metadata),
            product_slug=product_slug,
            changed_fields=changed_fields,
            job_id=job_id,
        )
        await db.document_versions.insert_one(version.model_dump())
        logger.debug(
            "Archived document version for %s (changed: %s)", existing_doc.url, changed_fields
        )
