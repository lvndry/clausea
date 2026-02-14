"""Migration script to rename companies collection to products and update company_id to product_id in documents.

This script:
1. Renames the 'companies' collection to 'products'
2. Updates all 'company_id' fields to 'product_id' in the 'documents' collection
3. Updates all 'company_slug' fields to 'product_slug' in product_overviews and deep_analyses collections
"""

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from src.core.config import config
from src.core.logging import get_logger

logger = get_logger(__name__)

MONGO_URI = config.database.mongodb_uri
DATABASE_NAME = "clausea"


async def migrate_companies_to_products():
    """Perform the migration from companies to products."""
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DATABASE_NAME]

    try:
        logger.info("Starting migration: companies -> products")

        # Step 1: Rename companies collection to products
        collections = await db.list_collection_names()
        if "companies" in collections:
            logger.info("Renaming 'companies' collection to 'products'...")
            await db.companies.rename("products")
            logger.info("✓ Renamed 'companies' collection to 'products'")
        elif "products" in collections:
            logger.info("'products' collection already exists, skipping rename")
        else:
            logger.warning("Neither 'companies' nor 'products' collection found")

        # Step 2: Update company_id to product_id in documents
        logger.info("Updating 'company_id' to 'product_id' in documents collection...")
        result = await db.documents.update_many(
            {"company_id": {"$exists": True}},
            {"$rename": {"company_id": "product_id"}},
        )
        logger.info(f"✓ Updated {result.modified_count} documents")

        # Step 3: Update company_slug to product_slug in product_overviews
        logger.info("Updating 'company_slug' to 'product_slug' in product_overviews collection...")
        result = await db.product_overviews.update_many(
            {"company_slug": {"$exists": True}},
            {"$rename": {"company_slug": "product_slug"}},
        )
        logger.info(f"✓ Updated {result.modified_count} product_overviews")

        # Step 4: Update company_slug to product_slug in deep_analyses
        logger.info("Updating 'company_slug' to 'product_slug' in deep_analyses collection...")
        result = await db.deep_analyses.update_many(
            {"company_slug": {"$exists": True}},
            {"$rename": {"company_slug": "product_slug"}},
        )
        logger.info(f"✓ Updated {result.modified_count} deep_analyses")

        # Step 5: Update company_id references in product_overviews and deep_analyses if they exist
        logger.info("Checking for company_id references in product_overviews...")
        result = await db.product_overviews.update_many(
            {"company_id": {"$exists": True}},
            {"$rename": {"company_id": "product_id"}},
        )
        if result.modified_count > 0:
            logger.info(f"✓ Updated {result.modified_count} product_overviews with company_id")

        logger.info("Checking for company_id references in deep_analyses...")
        result = await db.deep_analyses.update_many(
            {"company_id": {"$exists": True}},
            {"$rename": {"company_id": "product_id"}},
        )
        if result.modified_count > 0:
            logger.info(f"✓ Updated {result.modified_count} deep_analyses with company_id")

        logger.info("✅ Migration completed successfully!")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        raise
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(migrate_companies_to_products())
