"""Database index management for MongoDB collections.

This module ensures that all necessary indexes are created for optimal query performance.
Indexes are created idempotently - safe to run multiple times.
"""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.core.logging import get_logger

logger = get_logger(__name__)


async def ensure_product_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the products collection.

    Creates indexes for:
    - id: Unique index for primary key lookups
    - slug: Unique index for slug-based lookups

    Args:
        db: Database instance
    """
    collection = db.products

    # Create unique index on id field
    # Using create_index with background=True for non-blocking creation
    # and name parameter to ensure idempotency
    try:
        await collection.create_index("id", unique=True, name="idx_product_id", background=True)
        logger.info("Created unique index on products.id")
    except Exception as e:
        # Index might already exist or there might be duplicate values
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on products.id already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on products.id: {e}")

    # Create unique index on slug field
    try:
        await collection.create_index("slug", unique=True, name="idx_product_slug", background=True)
        logger.info("Created unique index on products.slug")
    except Exception as e:
        # Index might already exist or there might be duplicate values
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on products.slug already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on products.slug: {e}")


async def ensure_document_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the documents collection.

    Creates indexes for:
    - id: Unique index for primary key lookups
    - product_id: Index for product-based document queries (non-unique, multiple docs per product)

    Args:
        db: Database instance
    """
    collection = db.documents

    # Create unique index on id field
    # Using create_index with background=True for non-blocking creation
    # and name parameter to ensure idempotency
    try:
        await collection.create_index("id", unique=True, name="idx_document_id", background=True)
        logger.info("Created unique index on documents.id")
    except Exception as e:
        # Index might already exist or there might be duplicate values
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on documents.id already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on documents.id: {e}")

    # Create index on product_id field
    # Not unique since multiple documents can belong to the same product
    try:
        await collection.create_index("product_id", name="idx_document_product_id", background=True)
        logger.info("Created index on documents.product_id")
    except Exception as e:
        # Index might already exist
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("Index on documents.product_id already exists")
        else:
            logger.warning(f"Could not create index on documents.product_id: {e}")


async def ensure_all_indexes(db: AgnosticDatabase) -> None:
    """Ensure all database indexes are created.

    This function should be called during application startup to ensure
    all necessary indexes exist for optimal query performance.

    Args:
        db: Database instance
    """
    logger.info("Ensuring database indexes are created...")
    await ensure_product_indexes(db)
    await ensure_document_indexes(db)
    logger.info("Database indexes verified")
