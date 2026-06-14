"""Crawl repository for data access operations."""

from __future__ import annotations

from motor.core import AgnosticDatabase

from src.models.crawl import CrawlSession
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
