"""
This module contains the PromotionManager class, which is used to promote data from the local database to the production database.
"""

import os
from datetime import datetime
from typing import Any

import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.core.config import config
from src.core.logging import get_logger
from src.models.user import UserTier

load_dotenv()
logger = get_logger(__name__)


class PromotionManager:
    """
    This class is used to promote data from the local database to the production database.

    Promotion operations completely replace production collections with local data,
    not merging or diffing. All existing data in production collections is deleted
    before inserting the local data.
    """

    def __init__(self) -> None:
        local_uri = os.getenv("MONGO_URI")
        production_uri = os.getenv("PRODUCTION_MONGO_URI")
        self.database_name = config.database.mongodb_database

        if not local_uri:
            raise ValueError("MONGO_URI is not set")
        if not production_uri:
            raise ValueError("PRODUCTION_MONGO_URI is not set")

        self.local_uri: str = local_uri
        self.production_uri: str = production_uri

        self.local_client: AsyncIOMotorClient | None = None
        self.production_client: AsyncIOMotorClient | None = None
        self.local_db: AsyncIOMotorDatabase | None = None
        self.production_db: AsyncIOMotorDatabase | None = None

    async def connect_databases(self) -> None:
        """Connect to both local and production databases."""
        try:
            # Connect to local database
            if "+srv" in self.local_uri:
                self.local_client = AsyncIOMotorClient(
                    self.local_uri, tls=True, tlsCAFile=certifi.where()
                )
            else:
                self.local_client = AsyncIOMotorClient(self.local_uri)

            self.local_db = self.local_client[self.database_name]
            logger.info("Connected to local MongoDB")

            # Connect to production database
            if "+srv" in self.production_uri:
                self.production_client = AsyncIOMotorClient(
                    self.production_uri, tls=True, tlsCAFile=certifi.where()
                )
            else:
                self.production_client = AsyncIOMotorClient(self.production_uri)

            self.production_db = self.production_client[self.database_name]
            logger.info("Connected to production MongoDB")

        except Exception as e:
            logger.error(f"Error connecting to databases: {e}")
            raise e

    async def close_connections(self) -> None:
        """Close database connections."""
        if self.local_client:
            self.local_client.close()
        if self.production_client:
            self.production_client.close()
        logger.info("Closed database connections")

    async def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get statistics for a collection in both databases."""
        try:
            if self.local_db is None or self.production_db is None:
                raise ValueError("Database connections not established")

            local_count = await self.local_db[collection_name].count_documents({})
            production_count = await self.production_db[collection_name].count_documents({})

            return {
                "local_count": local_count,
                "production_count": production_count,
                "collection": collection_name,
            }
        except Exception as e:
            logger.error(f"Error getting stats for {collection_name}: {e}")
            return {
                "local_count": 0,
                "production_count": 0,
                "collection": collection_name,
            }

    async def promote_products(self, dry_run: bool = True) -> dict[str, Any]:
        """Promote products from local to production by completely replacing production collection."""
        try:
            if self.local_db is None or self.production_db is None:
                raise ValueError("Database connections not established")

            products = await self.local_db.products.find().to_list(length=None)
            local_count = len(products)
            deleted_count = 0
            inserted_count = 0
            errors = []

            if not dry_run:
                # Delete all existing products in production
                delete_result = await self.production_db.products.delete_many({})
                deleted_count = delete_result.deleted_count
                logger.info(f"Deleted {deleted_count} products from production")

                # Insert all products from local
                if products:
                    try:
                        await self.production_db.products.insert_many(products)
                        inserted_count = len(products)
                        logger.info(f"Inserted {inserted_count} products into production")
                    except Exception as e:
                        errors.append(f"Error inserting products: {str(e)}")
            else:
                # In dry run, just count what would be deleted
                production_count = await self.production_db.products.count_documents({})
                deleted_count = production_count
                inserted_count = local_count
                logger.info(
                    f"DRY RUN: Would delete {deleted_count} products and insert {inserted_count} products"
                )

            return {
                "local_count": local_count,
                "deleted_count": deleted_count,
                "inserted_count": inserted_count,
                "errors": errors,
                "dry_run": dry_run,
            }

        except Exception as e:
            logger.error(f"Error promoting products: {e}")
            return {
                "local_count": 0,
                "deleted_count": 0,
                "inserted_count": 0,
                "errors": [str(e)],
                "dry_run": dry_run,
            }

    async def promote_documents(self, dry_run: bool = True) -> dict[str, Any]:
        """Promote documents from local to production by completely replacing production collection."""
        try:
            if self.local_db is None or self.production_db is None:
                raise ValueError("Database connections not established")

            documents = await self.local_db.documents.find().to_list(length=None)
            local_count = len(documents)
            deleted_count = 0
            inserted_count = 0
            errors = []

            if not dry_run:
                # Delete all existing documents in production
                delete_result = await self.production_db.documents.delete_many({})
                deleted_count = delete_result.deleted_count
                logger.info(f"Deleted {deleted_count} documents from production")

                # Insert all documents from local
                if documents:
                    try:
                        await self.production_db.documents.insert_many(documents)
                        inserted_count = len(documents)
                        logger.info(f"Inserted {inserted_count} documents into production")
                    except Exception as e:
                        errors.append(f"Error inserting documents: {str(e)}")
            else:
                # In dry run, just count what would be deleted
                production_count = await self.production_db.documents.count_documents({})
                deleted_count = production_count
                inserted_count = local_count
                logger.info(
                    f"DRY RUN: Would delete {deleted_count} documents and insert {inserted_count} documents"
                )

            return {
                "local_count": local_count,
                "deleted_count": deleted_count,
                "inserted_count": inserted_count,
                "errors": errors,
                "dry_run": dry_run,
            }

        except Exception as e:
            logger.error(f"Error promoting documents: {e}")
            return {
                "local_count": 0,
                "deleted_count": 0,
                "inserted_count": 0,
                "errors": [str(e)],
                "dry_run": dry_run,
            }

    async def promote_product_overviews(self, dry_run: bool = True) -> dict[str, Any]:
        """Promote product overviews from local to production by completely replacing production collection."""
        try:
            if self.local_db is None or self.production_db is None:
                raise ValueError("Database connections not established")

            overviews = await self.local_db.product_overviews.find().to_list(length=None)
            local_count = len(overviews)
            deleted_count = 0
            inserted_count = 0
            errors = []

            if not dry_run:
                # Delete all existing product overviews in production
                delete_result = await self.production_db.product_overviews.delete_many({})
                deleted_count = delete_result.deleted_count
                logger.info(f"Deleted {deleted_count} product overviews from production")

                # Insert all product overviews from local
                if overviews:
                    try:
                        await self.production_db.product_overviews.insert_many(overviews)
                        inserted_count = len(overviews)
                        logger.info(f"Inserted {inserted_count} product overviews into production")
                    except Exception as e:
                        errors.append(f"Error inserting product overviews: {str(e)}")
            else:
                # In dry run, just count what would be deleted
                production_count = await self.production_db.product_overviews.count_documents({})
                deleted_count = production_count
                inserted_count = local_count
                logger.info(
                    f"DRY RUN: Would delete {deleted_count} product overviews and insert {inserted_count} product overviews"
                )

            return {
                "local_count": local_count,
                "deleted_count": deleted_count,
                "inserted_count": inserted_count,
                "errors": errors,
                "dry_run": dry_run,
            }

        except Exception as e:
            logger.error(f"Error promoting product overviews: {e}")
            return {
                "local_count": 0,
                "deleted_count": 0,
                "inserted_count": 0,
                "errors": [str(e)],
                "dry_run": dry_run,
            }

    async def promote_users_to_tier_system(self, dry_run: bool = True) -> dict[str, Any]:
        """Promote existing users to include tier and monthly_usage fields."""
        try:
            if self.local_db is None:
                raise ValueError("Database connections not established")

            logger.info("Starting user tier promotion...")

            # Get all users that don't have tier field
            users_without_tier = await self.local_db.users.find(
                {
                    "$or": [
                        {"tier": {"$exists": False}},
                        {"monthly_usage": {"$exists": False}},
                    ]
                }
            ).to_list(length=None)

            logger.info(f"Found {len(users_without_tier)} users to promote")

            promoted_count = 0
            skipped_count = 0
            errors = []

            for user_doc in users_without_tier:
                try:
                    user_id = user_doc.get("id")
                    if not user_id:
                        skipped_count += 1
                        continue

                    # Set default values for missing fields
                    update_data: dict[str, Any] = {}

                    if "tier" not in user_doc:
                        update_data["tier"] = UserTier.FREE.value
                        logger.info(f"Setting tier to FREE for user {user_id}")

                    if "monthly_usage" not in user_doc:
                        update_data["monthly_usage"] = {}
                        logger.info(f"Setting empty monthly_usage for user {user_id}")

                    if update_data:
                        update_data["updated_at"] = datetime.now()

                        if not dry_run:
                            await self.local_db.users.update_one(
                                {"id": user_id}, {"$set": update_data}
                            )
                        promoted_count += 1
                    else:
                        skipped_count += 1

                except Exception as e:
                    error_msg = f"Error promoting user {user_doc.get('id', 'unknown')}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            logger.info("User tier promotion completed successfully")

            return {
                "promoted": promoted_count,
                "skipped": skipped_count,
                "errors": errors,
                "dry_run": dry_run,
            }

        except Exception as e:
            logger.error(f"Error during user tier promotion: {e}")
            return {
                "promoted": 0,
                "skipped": 0,
                "errors": [str(e)],
                "dry_run": dry_run,
            }

    async def get_promotion_summary(self) -> dict[str, Any]:
        """Get a summary of all collections in both databases."""
        collections = [
            "products",
            "documents",
            "users",
            "conversations",
            "product_overviews",
        ]
        stats = {}

        for collection in collections:
            stats[collection] = await self.get_collection_stats(collection)

        return {
            "timestamp": datetime.now().isoformat(),
            "collections": stats,
            "local_uri": self.local_uri[:20] + "..."
            if len(self.local_uri) > 20
            else self.local_uri,
            "production_uri": self.production_uri[:20] + "..."
            if len(self.production_uri) > 20
            else self.production_uri,
        }

    async def run_full_promotion(self, dry_run: bool = True) -> dict[str, Any]:
        """Run a full promotion of all data."""
        try:
            await self.connect_databases()

            summary = await self.get_promotion_summary()
            products_result = await self.promote_products(dry_run)
            documents_result = await self.promote_documents(dry_run)
            product_overviews_result = await self.promote_product_overviews(dry_run)
            users_result = await self.promote_users_to_tier_system(dry_run)

            return {
                "summary": summary,
                "products": products_result,
                "documents": documents_result,
                "product_overviews": product_overviews_result,
                "users": users_result,
                "dry_run": dry_run,
                "timestamp": datetime.now().isoformat(),
            }

        finally:
            await self.close_connections()
