"""Repository for slim document_changes collection."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.document import Document
from src.models.document_change import DocumentChange
from src.repositories.base_repository import BaseRepository


class DocumentChangeRepository(BaseRepository):
    COLLECTION = "document_changes"

    async def record(self, db: AgnosticDatabase, change: DocumentChange) -> None:
        await db[self.COLLECTION].insert_one(change.model_dump(mode="json"))

    async def record_document_update(
        self,
        db: AgnosticDatabase,
        *,
        existing_doc: Document,
        changed_fields: list[str],
        job_id: str | None = None,
        previous_hash: str | None = None,
    ) -> None:
        product_slug: str | None = None
        if existing_doc.product_id:
            product = await db.products.find_one({"id": existing_doc.product_id}, {"slug": 1})
            if product:
                product_slug = product.get("slug")

        if not existing_doc.product_id:
            return

        if not existing_doc.content_hash:
            return

        await self.record(
            db,
            DocumentChange(
                document_id=existing_doc.id,
                product_id=existing_doc.product_id,
                product_slug=product_slug,
                content_hash=existing_doc.content_hash,
                previous_hash=previous_hash,
                changed_fields=changed_fields,
                job_id=job_id,
            ),
        )

    async def list_for_document(
        self, db: AgnosticDatabase, document_id: str, *, limit: int = 50
    ) -> list[DocumentChange]:
        cursor = (
            db[self.COLLECTION]
            .find({"document_id": document_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        rows = await cursor.to_list(length=limit)
        return [DocumentChange.model_validate(row) for row in rows]

    async def delete_for_product(self, db: AgnosticDatabase, product_id: str) -> int:
        result = await db[self.COLLECTION].delete_many({"product_id": product_id})
        return result.deleted_count
