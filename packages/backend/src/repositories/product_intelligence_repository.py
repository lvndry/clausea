"""Repository for unified product_intelligence collection."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.core import AgnosticDatabase

from src.models.product_intelligence import OverviewSnapshot, ProductIntelligence, ProductRollup
from src.repositories.base_repository import BaseRepository


def _row_to_intelligence(row: dict[str, Any] | None) -> ProductIntelligence | None:
    if not row:
        return None
    data = dict(row)
    data.pop("_id", None)
    return ProductIntelligence.model_validate(data)


class ProductIntelligenceRepository(BaseRepository):
    COLLECTION = "product_intelligence"

    async def get_by_product_id(
        self, db: AgnosticDatabase, product_id: str
    ) -> ProductIntelligence | None:
        row = await db[self.COLLECTION].find_one({"product_id": product_id})
        return _row_to_intelligence(row)

    async def get_by_slug(
        self, db: AgnosticDatabase, product_slug: str
    ) -> ProductIntelligence | None:
        row = await db[self.COLLECTION].find_one({"product_slug": product_slug})
        return _row_to_intelligence(row)

    async def ensure_shell(
        self, db: AgnosticDatabase, *, product_id: str, product_slug: str
    ) -> ProductIntelligence:
        existing = await self.get_by_product_id(db, product_id)
        if existing:
            return existing
        now = datetime.now()
        shell = ProductIntelligence(product_id=product_id, product_slug=product_slug)
        await db[self.COLLECTION].update_one(
            {"product_id": product_id},
            {
                "$setOnInsert": {
                    **shell.model_dump(mode="json"),
                    "generated_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )
        return (await self.get_by_product_id(db, product_id)) or shell

    async def upsert(self, db: AgnosticDatabase, intelligence: ProductIntelligence) -> None:
        data = intelligence.model_dump(mode="json")
        data["updated_at"] = datetime.now()
        await db[self.COLLECTION].update_one(
            {"product_id": intelligence.product_id},
            {"$set": data},
            upsert=True,
        )

    async def upsert_fields(
        self, db: AgnosticDatabase, product_id: str, fields: dict[str, Any]
    ) -> None:
        fields = dict(fields)
        fields["updated_at"] = datetime.now()
        await db[self.COLLECTION].update_one(
            {"product_id": product_id},
            {"$set": fields},
            upsert=True,
        )

    async def upsert_rollup(
        self,
        db: AgnosticDatabase,
        *,
        product_id: str,
        product_slug: str,
        rollup: ProductRollup,
        source_hashes: dict[str, str],
    ) -> None:
        now = datetime.now()
        await db[self.COLLECTION].update_one(
            {"product_id": product_id},
            {
                "$set": {
                    "product_id": product_id,
                    "product_slug": product_slug,
                    "rollup": rollup.model_dump(mode="json"),
                    "source_hashes": source_hashes,
                    "rollup_generated_at": now,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "id": ProductIntelligence(product_id=product_id, product_slug=product_slug).id,
                    "generated_at": now,
                },
            },
            upsert=True,
        )

    async def delete_for_product(self, db: AgnosticDatabase, product_id: str) -> int:
        result = await db[self.COLLECTION].delete_many({"product_id": product_id})
        return result.deleted_count

    async def count_with_overview(self, db: AgnosticDatabase) -> int:
        return await db[self.COLLECTION].count_documents(
            {"overview": {"$exists": True, "$ne": None}}
        )

    async def list_overview_history(
        self, db: AgnosticDatabase, product_slug: str, limit: int = 50
    ) -> list[OverviewSnapshot]:
        intelligence = await self.get_by_slug(db, product_slug)
        if not intelligence:
            return []
        return intelligence.overview_history[:limit]

    async def list_sitemap_entries(self, db: AgnosticDatabase) -> list[dict[str, Any]]:
        cursor = db[self.COLLECTION].find(
            {"overview": {"$exists": True, "$ne": None}},
            {"_id": 0, "product_slug": 1, "overview_generated_at": 1, "updated_at": 1},
        )
        rows = await cursor.to_list(length=None)
        return [
            {
                "product_slug": row.get("product_slug"),
                "updated_at": row.get("overview_generated_at") or row.get("updated_at"),
            }
            for row in rows
            if row.get("product_slug")
        ]
