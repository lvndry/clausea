"""Document version repository for data access operations."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.document_version import DocumentVersion
from src.repositories.base_repository import BaseRepository


class DocumentVersionRepository(BaseRepository):
    """Repository for document versions."""

    async def create(self, db: AgnosticDatabase, version: DocumentVersion) -> DocumentVersion:
        await db.document_versions.insert_one(version.model_dump())
        return version

    async def find_by_id(self, db: AgnosticDatabase, version_id: str) -> DocumentVersion | None:
        data = await db.document_versions.find_one({"id": version_id})
        return DocumentVersion(**data) if data else None

    async def find_latest_for_document(
        self, db: AgnosticDatabase, document_id: str
    ) -> DocumentVersion | None:
        data = await db.document_versions.find_one(
            {"document_id": document_id}, sort=[("created_at", -1)]
        )
        return DocumentVersion(**data) if data else None

    async def find_by_document(
        self, db: AgnosticDatabase, document_id: str
    ) -> list[DocumentVersion]:
        items = await db.document_versions.find({"document_id": document_id}).to_list(length=None)
        return [DocumentVersion(**item) for item in items]

    async def update(self, db: AgnosticDatabase, version: DocumentVersion) -> bool:
        result = await db.document_versions.update_one(
            {"id": version.id}, {"$set": version.model_dump()}
        )
        return result.modified_count > 0
