"""Document section repository for data access operations."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.document_section import DocumentSection
from src.repositories.base_repository import BaseRepository


class DocumentSectionRepository(BaseRepository):
    """Repository for document sections."""

    async def create_many(self, db: AgnosticDatabase, sections: list[DocumentSection]) -> int:
        if not sections:
            return 0
        result = await db.document_sections.insert_many([s.model_dump() for s in sections])
        return len(result.inserted_ids)

    async def find_by_version(self, db: AgnosticDatabase, version_id: str) -> list[DocumentSection]:
        items = await db.document_sections.find({"version_id": version_id}).to_list(length=None)
        return [DocumentSection(**item) for item in items]
