"""Database session management for MongoDB using Motor.

This module provides a context manager for creating database sessions
that are properly bound to the current event loop, solving threading
issues with Streamlit and ensuring clean connection lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import certifi
from motor.core import AgnosticDatabase
from motor.motor_asyncio import AsyncIOMotorClient

from src.core.config import config
from src.core.logging import get_logger

logger = get_logger(__name__)


DATABASE_NAME = "clausea"
MONGO_URI = config.database.mongodb_uri


@asynccontextmanager
async def get_db() -> AsyncIterator[AgnosticDatabase]:
    """Create a database session in the current event loop.

    This context manager ensures:
    - Motor client is created in the correct event loop (important for threading)
    - Connection is properly closed after use
    - Each request/thread gets its own isolated database session

    Usage:
        async with get_db() as db:
            # Use db for queries
            result = await db.products.find_one({"slug": "example"})

    Yields:
        AgnosticDatabase: MongoDB database instance bound to current event loop
    """
    # Create Motor client in the current event loop
    if "+srv" in MONGO_URI:
        client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    else:
        client = AsyncIOMotorClient(MONGO_URI)

    db = client[DATABASE_NAME]

    logger.debug(f"Created DB session in event loop: {id(db)}")

    try:
        yield db
    finally:
        # Clean up the connection
        client.close()
        logger.debug(f"Closed DB session: {id(db)}")


async def test_db_connection() -> bool:
    """Test database connection using the context manager.

    Returns:
        bool: True if connection successful
    """
    try:
        async with get_db() as db:
            # Test connection
            await db.command("ping")
            logger.info("Successfully connected to MongoDB")
            return True
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return False
