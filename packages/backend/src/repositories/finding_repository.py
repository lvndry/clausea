"""Finding repository for data access operations."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.finding import Aggregation, Finding
from src.repositories.base_repository import BaseRepository


class FindingRepository(BaseRepository):
    """Repository for findings and aggregations."""

    async def create_many(self, db: AgnosticDatabase, findings: list[Finding]) -> int:
        if not findings:
            return 0
        result = await db.findings.insert_many([f.model_dump() for f in findings])
        return len(result.inserted_ids)

    async def find_by_document(self, db: AgnosticDatabase, document_id: str) -> list[Finding]:
        items = await db.findings.find({"document_id": document_id}).to_list(length=None)
        return [Finding(**item) for item in items]

    async def find_by_product(self, db: AgnosticDatabase, product_id: str) -> list[Finding]:
        items = await db.findings.find({"product_id": product_id}).to_list(length=None)
        return [Finding(**item) for item in items]

    async def save_aggregation(self, db: AgnosticDatabase, aggregation: Aggregation) -> None:
        data = aggregation.model_dump()
        await db.aggregations.update_one(
            {"product_id": aggregation.product_id}, {"$set": data}, upsert=True
        )

    async def get_aggregation(self, db: AgnosticDatabase, product_id: str) -> Aggregation | None:
        data = await db.aggregations.find_one({"product_id": product_id})
        return Aggregation(**data) if data else None

    async def delete_findings_for_document(self, db: AgnosticDatabase, document_id: str) -> int:
        result = await db.findings.delete_many({"document_id": document_id})
        return result.deleted_count

    async def delete_aggregation(self, db: AgnosticDatabase, product_id: str) -> int:
        result = await db.aggregations.delete_one({"product_id": product_id})
        return result.deleted_count
