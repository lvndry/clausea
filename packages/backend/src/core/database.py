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


_motor_clients: dict[int, AsyncIOMotorClient] = {}

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
    (e.g., in a threaded Streamlit context), we create a new client for that loop.
    """
    global _motor_clients

    loop = asyncio.get_running_loop()
    loop_id = id(loop)

    if loop_id not in _motor_clients:
        _motor_clients[loop_id] = _create_motor_client()
        logger.info(f"Initialized MongoDB client for loop {loop_id}")

    return _motor_clients[loop_id]


def close_motor_client(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Close the Motor client bound to *loop*.

    When called from a worker thread there may not be a running event loop,
    so callers can pass the loop explicitly. If no loop is provided we fall
    back to the current running loop.
    """
    global _motor_clients

    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No running event loop available when closing MongoDB client")
            return

    loop_id = id(loop)

    if loop_id in _motor_clients:
        _motor_clients[loop_id].close()
        del _motor_clients[loop_id]
        logger.info(f"Closed MongoDB client for loop {loop_id}")


async def get_db() -> AsyncIterator[AgnosticDatabase]:
    """FastAPI dependency that yields a database bound to current event loop.

    This dependency ensures:
    - Motor client is created in the correct event loop (important for threading)
    - A single shared client is reused (connection pool)

    Yields:
        AgnosticDatabase: MongoDB database instance bound to current event loop
    """
    client = get_motor_client()
    db = client[DATABASE_NAME]
    if is_db_dry_run():
        yield DryRunDatabase(db, enabled=True)  # type: ignore[return-value]
    else:
        yield db


@asynccontextmanager
async def db_session() -> AsyncIterator[AgnosticDatabase]:
    """Context-manager wrapper for scripts/background tasks.

    Usage:
        async with db_session() as db:
            result = await db.products.find_one({"slug": "example"})
    """
    async for db in get_db():
        yield db


async def test_db_connection() -> bool:
    """Test database connection using the context manager.

    Returns:
        bool: True if connection successful
    """
    try:
        async with db_session() as db:
            # Test connection
            await db.command("ping")
            logger.info("Successfully connected to MongoDB")
            return True
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return False
