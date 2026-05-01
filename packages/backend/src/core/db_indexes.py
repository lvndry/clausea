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

    try:
        await collection.create_index("domains", name="idx_product_domains", background=True)
        logger.info("Created index on products.domains")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("Index on products.domains already exists")
        else:
            logger.warning(f"Could not create index on products.domains: {e}")


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

    try:
        await collection.create_index("url", unique=True, name="idx_document_url", background=True)
        logger.info("Created unique index on documents.url")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on documents.url already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on documents.url: {e}")


async def ensure_user_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the users collection."""
    try:
        await db.users.create_index("id", unique=True, name="idx_user_id", background=True)
        logger.info("Created unique index on users.id")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on users.id already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on users.id: {e}")

    try:
        await db.users.create_index("email", unique=True, name="idx_user_email", background=True)
        logger.info("Created unique index on users.email")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on users.email already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on users.email: {e}")


async def ensure_conversation_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the conversations collection."""
    try:
        await db.conversations.create_index(
            "id", unique=True, name="idx_conversation_id", background=True
        )
        logger.info("Created unique index on conversations.id")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on conversations.id already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on conversations.id: {e}")

    try:
        await db.conversations.create_index(
            [("user_id", 1), ("last_message_at", -1)],
            name="idx_conversation_user_recent",
            background=True,
        )
        logger.info("Created index on conversations.(user_id, last_message_at)")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("Index on conversations.(user_id, last_message_at) already exists")
        else:
            logger.warning(
                f"Could not create index on conversations.(user_id, last_message_at): {e}"
            )


async def ensure_finding_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the findings collection."""
    try:
        await db.findings.create_index("product_id", name="idx_finding_product_id", background=True)
        logger.info("Created index on findings.product_id")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("Index on findings.product_id already exists")
        else:
            logger.warning(f"Could not create index on findings.product_id: {e}")

    try:
        await db.findings.create_index(
            "document_id", name="idx_finding_document_id", background=True
        )
        logger.info("Created index on findings.document_id")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("Index on findings.document_id already exists")
        else:
            logger.warning(f"Could not create index on findings.document_id: {e}")


async def ensure_product_overview_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the product_overviews collection."""
    try:
        await db.product_overviews.create_index(
            "product_slug", unique=True, name="idx_overview_slug", background=True
        )
        logger.info("Created unique index on product_overviews.product_slug")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug(
                "Index on product_overviews.product_slug already exists or has duplicate values"
            )
        else:
            logger.warning(f"Could not create index on product_overviews.product_slug: {e}")


async def ensure_deep_analysis_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the deep_analyses collection."""
    try:
        await db.deep_analyses.create_index(
            "product_slug", unique=True, name="idx_deep_analysis_slug", background=True
        )
        logger.info("Created unique index on deep_analyses.product_slug")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug(
                "Index on deep_analyses.product_slug already exists or has duplicate values"
            )
        else:
            logger.warning(f"Could not create index on deep_analyses.product_slug: {e}")


async def ensure_aggregation_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the aggregations collection."""
    try:
        await db.aggregations.create_index(
            "product_id", unique=True, name="idx_aggregation_product_id", background=True
        )
        logger.info("Created unique index on aggregations.product_id")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on aggregations.product_id already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on aggregations.product_id: {e}")


async def ensure_document_version_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on the document_versions collection."""
    try:
        await db.document_versions.create_index(
            [("document_id", 1), ("created_at", -1)],
            name="idx_docversion_doc_recent",
            background=True,
        )
        logger.info("Created index on document_versions.(document_id, created_at)")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("Index on document_versions.(document_id, created_at) already exists")
        else:
            logger.warning(
                f"Could not create index on document_versions.(document_id, created_at): {e}"
            )


async def ensure_pipeline_indexes(db: AgnosticDatabase) -> None:
    """Ensure indexes exist on pipeline-related collections."""
    # pipeline_jobs
    try:
        await db.pipeline_jobs.create_index(
            "id", unique=True, name="idx_pipeline_job_id", background=True
        )
        logger.info("Created unique index on pipeline_jobs.id")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug("Index on pipeline_jobs.id already exists or has duplicate values")
        else:
            logger.warning(f"Could not create index on pipeline_jobs.id: {e}")

    try:
        await db.pipeline_jobs.create_index(
            "product_slug", name="idx_pipeline_job_product_slug", background=True
        )
        logger.info("Created index on pipeline_jobs.product_slug")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("Index on pipeline_jobs.product_slug already exists")
        else:
            logger.warning(f"Could not create index on pipeline_jobs.product_slug: {e}")

    # indexation_subscriptions
    try:
        await db.indexation_subscriptions.create_index(
            [("product_slug", 1), ("email", 1)],
            unique=True,
            name="idx_indexation_sub_product_email",
            background=True,
        )
        logger.info("Created unique index on indexation_subscriptions.(product_slug,email)")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug(
                "Index on indexation_subscriptions.(product_slug,email) already exists or has duplicates"
            )
        else:
            logger.warning(f"Could not create index on indexation_subscriptions: {e}")


async def ensure_all_indexes(db: AgnosticDatabase) -> None:
    """Ensure all database indexes are created.

    This function should be called during application startup to ensure
    all necessary indexes exist for optimal query performance.

    Args:
        db: Database instance
    """
    logger.info("Ensuring database indexes are created...")
    await ensure_user_indexes(db)
    await ensure_conversation_indexes(db)
    await ensure_product_indexes(db)
    await ensure_document_indexes(db)
    await ensure_finding_indexes(db)
    await ensure_product_overview_indexes(db)
    await ensure_deep_analysis_indexes(db)
    await ensure_aggregation_indexes(db)
    await ensure_document_version_indexes(db)
    await ensure_pipeline_indexes(db)

    # TTL indexes for ephemeral crawl data
    try:
        await db.crawl_events.create_index(
            "created_at",
            expireAfterSeconds=7 * 24 * 3600,
            name="ttl_crawl_events_7d",
            background=True,
        )
        logger.info("Created TTL index on crawl_events.created_at")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("TTL index on crawl_events.created_at already exists")
        else:
            logger.warning(f"Could not create TTL index on crawl_events.created_at: {e}")

    try:
        await db.crawl_targets.create_index(
            "created_at",
            expireAfterSeconds=7 * 24 * 3600,
            name="ttl_crawl_targets_7d",
            background=True,
        )
        logger.info("Created TTL index on crawl_targets.created_at")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("TTL index on crawl_targets.created_at already exists")
        else:
            logger.warning(f"Could not create TTL index on crawl_targets.created_at: {e}")

    # Extension anonymous usage tracking
    try:
        await db.extension_anonymous_usage.create_index(
            "last_seen",
            expireAfterSeconds=60 * 60 * 24 * 30,
            name="ttl_extension_usage_30d",
            background=True,
        )
        logger.info("Created TTL index on extension_anonymous_usage.last_seen")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg:
            logger.debug("TTL index on extension_anonymous_usage.last_seen already exists")
        else:
            logger.warning(
                f"Could not create TTL index on extension_anonymous_usage.last_seen: {e}"
            )

    try:
        await db.extension_anonymous_usage.create_index(
            "token", unique=True, name="idx_extension_usage_token", background=True
        )
        logger.info("Created unique index on extension_anonymous_usage.token")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.debug(
                "Unique index on extension_anonymous_usage.token already exists or has duplicate values"
            )
        else:
            logger.warning(f"Could not create unique index on extension_anonymous_usage.token: {e}")

    logger.info("Database indexes verified")
