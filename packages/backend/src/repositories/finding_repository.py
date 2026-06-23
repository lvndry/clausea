"""Legacy findings repository — deprecated; findings are built in memory from extractions."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.finding import Finding
from src.repositories.base_repository import BaseRepository


class FindingRepository(BaseRepository):
    async def create_many(self, db: AgnosticDatabase, findings: list[Finding]) -> int:
        raise NotImplementedError("findings collection is deprecated")

    async def find_by_product(self, db: AgnosticDatabase, product_id: str) -> list[Finding]:
        items = await db.findings.find({"product_id": product_id}).to_list(length=None)
        return [Finding(**item) for item in items]

    async def delete_findings_for_document(self, db: AgnosticDatabase, document_id: str) -> int:
        result = await db.findings.delete_many({"document_id": document_id})
        return result.deleted_count

    async def delete_findings_for_product(self, db: AgnosticDatabase, product_id: str) -> int:
        result = await db.findings.delete_many({"product_id": product_id})
        return result.deleted_count

    async def has_findings_for_document(self, db: AgnosticDatabase, document_id: str) -> bool:
        doc = await db.findings.find_one({"document_id": document_id}, projection={"_id": 1})
        return doc is not None
