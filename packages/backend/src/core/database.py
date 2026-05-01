"""Database session management for MongoDB using Motor."""

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


_motor_clients: dict[int, tuple[AsyncIOMotorClient, asyncio.AbstractEventLoop]] = {}

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
    """Return a shared Motor client for the current event loop (connection pool)."""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)

    entry = _motor_clients.get(loop_id)
    if entry is not None:
        client, stored_loop = entry
        if stored_loop is loop:
            return client
        # Loop ID was reused after GC — close stale client and recreate.
        client.close()

    client = _create_motor_client()
    _motor_clients[loop_id] = (client, loop)
    logger.info(f"Initialized MongoDB client for loop {loop_id}")
    return client


def close_motor_client(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Close the Motor client bound to *loop* (or the running loop if omitted)."""
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No running event loop available when closing MongoDB client")
            return

    loop_id = id(loop)
    entry = _motor_clients.pop(loop_id, None)
    if entry is not None:
        client, _ = entry
        client.close()
        logger.info(f"Closed MongoDB client for loop {loop_id}")


async def get_db() -> AsyncIterator[AgnosticDatabase]:
    """FastAPI dependency — yields a database session for the current event loop."""
    client = get_motor_client()
    db = client[DATABASE_NAME]
    if is_db_dry_run():
        yield DryRunDatabase(db, enabled=True)  # type: ignore[return-value]
    else:
        yield db


@asynccontextmanager
async def db_session() -> AsyncIterator[AgnosticDatabase]:
    """Context manager for scripts and background tasks.

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
