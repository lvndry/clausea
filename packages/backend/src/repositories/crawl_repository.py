"""Crawl repository for data access operations."""

from __future__ import annotations

from typing import Any

from motor.core import AgnosticDatabase

from src.models.crawl import CrawlEvent, CrawlSession, CrawlTarget
from src.repositories.base_repository import BaseRepository


class CrawlRepository(BaseRepository):
    """Repository for crawl sessions, targets, and events."""

    async def create_session(self, db: AgnosticDatabase, session: CrawlSession) -> CrawlSession:
        await db.crawl_sessions.insert_one(session.model_dump())
        return session

    async def update_session(self, db: AgnosticDatabase, session: CrawlSession) -> bool:
        result = await db.crawl_sessions.update_one(
            {"id": session.id}, {"$set": session.model_dump()}
        )
        return result.modified_count > 0

    async def find_session(self, db: AgnosticDatabase, session_id: str) -> CrawlSession | None:
        data = await db.crawl_sessions.find_one({"id": session_id})
        return CrawlSession(**data) if data else None

    async def add_targets(self, db: AgnosticDatabase, targets: list[CrawlTarget]) -> int:
        if not targets:
            return 0
        result = await db.crawl_targets.insert_many([t.model_dump() for t in targets])
        return len(result.inserted_ids)

    async def update_target(self, db: AgnosticDatabase, target: CrawlTarget) -> bool:
        result = await db.crawl_targets.update_one({"id": target.id}, {"$set": target.model_dump()})
        return result.modified_count > 0

    async def find_targets_by_session(
        self, db: AgnosticDatabase, session_id: str, status: str | None = None
    ) -> list[CrawlTarget]:
        query: dict[str, Any] = {"session_id": session_id}
        if status:
            query["status"] = status
        items = await db.crawl_targets.find(query).to_list(length=None)
        return [CrawlTarget(**item) for item in items]

    async def add_event(self, db: AgnosticDatabase, event: CrawlEvent) -> CrawlEvent:
        await db.crawl_events.insert_one(event.model_dump())
        return event
