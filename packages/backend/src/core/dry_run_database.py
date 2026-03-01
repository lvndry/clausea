from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class DryRunInsertOneResult:
    inserted_id: str


@dataclass(slots=True)
class DryRunInsertManyResult:
    inserted_ids: list[str]


@dataclass(slots=True)
class DryRunUpdateResult:
    matched_count: int = 0
    modified_count: int = 0
    upserted_id: str | None = None


@dataclass(slots=True)
class DryRunDeleteResult:
    deleted_count: int = 0


@runtime_checkable
class _MotorCollectionLike(Protocol):
    name: str


class DryRunCollection:
    """Wrap a Motor collection and no-op any writes.

    Reads are passed through to the underlying collection.
    """

    def __init__(self, collection: Any, *, enabled: bool = True) -> None:
        self._collection = collection
        self._enabled = enabled

    def __getattr__(self, name: str) -> Any:
        # Pass through everything we don't explicitly override.
        return getattr(self._collection, name)

    @property
    def name(self) -> str:
        return getattr(self._collection, "name", "<unknown>")

    def _fake_id(self) -> str:
        return uuid.uuid4().hex

    async def insert_one(self, *args: Any, **kwargs: Any) -> DryRunInsertOneResult:
        if self._enabled:
            logger.debug("DRY RUN: insert_one skipped", collection=self.name)
            return DryRunInsertOneResult(inserted_id=self._fake_id())
        return await self._collection.insert_one(*args, **kwargs)

    async def insert_many(self, documents: list[dict[str, Any]], *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug(
                "DRY RUN: insert_many skipped",
                collection=self.name,
                documents_count=len(documents),
            )
            return DryRunInsertManyResult(inserted_ids=[self._fake_id() for _ in documents])
        return await self._collection.insert_many(documents, *args, **kwargs)

    async def update_one(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: update_one skipped", collection=self.name)
            return DryRunUpdateResult()
        return await self._collection.update_one(*args, **kwargs)

    async def update_many(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: update_many skipped", collection=self.name)
            return DryRunUpdateResult()
        return await self._collection.update_many(*args, **kwargs)

    async def replace_one(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: replace_one skipped", collection=self.name)
            return DryRunUpdateResult()
        return await self._collection.replace_one(*args, **kwargs)

    async def delete_one(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: delete_one skipped", collection=self.name)
            return DryRunDeleteResult()
        return await self._collection.delete_one(*args, **kwargs)

    async def delete_many(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: delete_many skipped", collection=self.name)
            return DryRunDeleteResult()
        return await self._collection.delete_many(*args, **kwargs)

    async def bulk_write(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: bulk_write skipped", collection=self.name)
            # Some callers may inspect modified_count etc; keep parity with update results.
            return DryRunUpdateResult()
        return await self._collection.bulk_write(*args, **kwargs)

    async def find_one_and_update(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: find_one_and_update skipped", collection=self.name)
            return None
        return await self._collection.find_one_and_update(*args, **kwargs)

    async def find_one_and_replace(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: find_one_and_replace skipped", collection=self.name)
            return None
        return await self._collection.find_one_and_replace(*args, **kwargs)

    async def find_one_and_delete(self, *args: Any, **kwargs: Any) -> Any:
        if self._enabled:
            logger.debug("DRY RUN: find_one_and_delete skipped", collection=self.name)
            return None
        return await self._collection.find_one_and_delete(*args, **kwargs)


class DryRunDatabase:
    """Wrap a Motor database and return write-blocking collections."""

    def __init__(self, db: Any, *, enabled: bool = True) -> None:
        self._db = db
        self._enabled = enabled

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._db, name)
        # Motor exposes collections as attributes (e.g. db.documents).
        # If it looks like a collection, wrap it.
        if hasattr(value, "find") and hasattr(value, "insert_one"):
            return DryRunCollection(value, enabled=self._enabled)
        return value

    def __getitem__(self, name: str) -> Any:
        # Motor exposes collections via subscription (e.g. db["pipeline_jobs"]).
        collection = self._db[name]
        return DryRunCollection(collection, enabled=self._enabled)
