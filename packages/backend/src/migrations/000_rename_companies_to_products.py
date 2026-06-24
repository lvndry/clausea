"""Rename companies collection to products and remap company_* field references.

1. Renames the 'companies' collection to 'products'.
2. Updates all 'company_id' fields to 'product_id' in the 'documents' collection.
3. Updates all 'company_slug' fields to 'product_slug' in product_intelligence.
4. Updates any remaining 'company_id' references in product_intelligence.

Idempotent: the rename is skipped once 'products' exists, and every ``$rename``
is guarded by ``$exists`` so re-runs touch zero documents.
"""

from __future__ import annotations

import asyncio
from typing import Any

from motor.core import AgnosticDatabase

from src.core.database import db_session
from src.core.logging import get_logger
from src.migrations.base import Migration

logger = get_logger(__name__)


async def migrate_companies_to_products(db: AgnosticDatabase) -> dict[str, Any]:
    """Perform the migration from companies to products against ``db``."""
    detail: dict[str, Any] = {}

    collections = await db.list_collection_names()
    if "companies" in collections:
        logger.info("Renaming 'companies' collection to 'products'...")
        await db.companies.rename("products")
        detail["renamed_collection"] = True
    elif "products" in collections:
        logger.info("'products' collection already exists, skipping rename")
        detail["renamed_collection"] = False
    else:
        logger.warning("Neither 'companies' nor 'products' collection found")
        detail["renamed_collection"] = False

    result = await db.documents.update_many(
        {"company_id": {"$exists": True}},
        {"$rename": {"company_id": "product_id"}},
    )
    detail["documents_renamed"] = result.modified_count

    result = await db.product_intelligence.update_many(
        {"company_slug": {"$exists": True}},
        {"$rename": {"company_slug": "product_slug"}},
    )
    detail["product_intelligence_slug_renamed"] = result.modified_count

    result = await db.product_intelligence.update_many(
        {"company_id": {"$exists": True}},
        {"$rename": {"company_id": "product_id"}},
    )
    detail["product_intelligence_id_renamed"] = result.modified_count

    logger.info("companies -> products migration complete", **detail)
    return detail


class MigrateCompaniesToProducts(Migration):
    migration_id = "000_rename_companies_to_products"
    description = "Rename companies collection to products and remap company_* fields"

    async def upgrade(self, db: AgnosticDatabase) -> dict[str, Any]:
        return await migrate_companies_to_products(db)


if __name__ == "__main__":

    async def _run() -> None:
        async with db_session() as db:
            await migrate_companies_to_products(db)

    asyncio.run(_run())
