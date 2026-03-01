"""Database session management for MongoDB using Motor.

This module provides a context manager for creating database sessions
that are properly bound to the current event loop, solving threading
issues with Streamlit and ensuring clean connection lifecycle.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

import certifi
from motor.core import AgnosticDatabase
from motor.motor_asyncio import AsyncIOMotorClient

from src.core.config import config
from src.core.dry_run_database import DryRunDatabase
from src.core.logging import get_logger

logger = get_logger(__name__)


DATABASE_NAME = "clausea"
MONGO_URI = config.database.mongodb_uri


_motor_client: AsyncIOMotorClient | None = None
_motor_client_loop_id: int | None = None

_db_dry_run: ContextVar[bool] = ContextVar("db_dry_run", default=False)


def is_db_dry_run() -> bool:
    return bool(_db_dry_run.get())


@contextmanager
def db_dry_run(enabled: bool = True) -> Iterator[None]:
    """Enable/disable DB dry-run within the current context.

    When enabled, `get_db()` yields a write-blocking proxy (reads still hit MongoDB).
    """
    token = _db_dry_run.set(bool(enabled))
    try:
        yield
    finally:
        _db_dry_run.reset(token)


def _create_motor_client() -> AsyncIOMotorClient:
    if "+srv" in MONGO_URI:
        return AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    return AsyncIOMotorClient(MONGO_URI)


def get_motor_client() -> AsyncIOMotorClient:
    """Return a shared Motor client (connection pool).

    In typical FastAPI usage we want a single process-wide client to avoid
    reconnecting on every request. If the active asyncio event loop changes
    (e.g., in a threaded Streamlit context), we re-create the client.
    """
    global _motor_client, _motor_client_loop_id

    loop = asyncio.get_running_loop()
    loop_id = id(loop)

    if _motor_client is None or _motor_client_loop_id != loop_id:
        if _motor_client is not None:
            _motor_client.close()
        _motor_client = _create_motor_client()
        _motor_client_loop_id = loop_id
        logger.info("Initialized MongoDB client")

    return _motor_client


def close_motor_client() -> None:
    global _motor_client, _motor_client_loop_id

    if _motor_client is None:
        return

    _motor_client.close()
    _motor_client = None
    _motor_client_loop_id = None
    logger.info("Closed MongoDB client")


@asynccontextmanager
async def get_db() -> AsyncIterator[AgnosticDatabase]:
    """Create a database session in the current event loop.

    This context manager ensures:
    - Motor client is created in the correct event loop (important for threading)
    - A single shared client is reused (connection pool)

    Usage:
        async with get_db() as db:
            # Use db for queries
            result = await db.products.find_one({"slug": "example"})

    Yields:
        AgnosticDatabase: MongoDB database instance bound to current event loop
    """
    client = get_motor_client()
    db = client[DATABASE_NAME]
    if is_db_dry_run():
        yield DryRunDatabase(db, enabled=True)  # type: ignore[return-value]
    else:
        yield db


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
