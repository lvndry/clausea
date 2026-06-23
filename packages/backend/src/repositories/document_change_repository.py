"""Repository for slim document_changes collection."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.document_change import DocumentChange
from src.repositories.base_repository import BaseRepository


class DocumentChangeRepository(BaseRepository):
    COLLECTION = "document_changes"

    async def record(self, db: AgnosticDatabase, change: DocumentChange) -> None:
        await db[self.COLLECTION].insert_one(change.model_dump(mode="json"))

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
