"""Backfill document_versions and document_sections from existing documents."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime

from src.core.database import db_session
from src.core.logging import get_logger
from src.models.document_section import DocumentSection
from src.models.document_version import DocumentVersion

logger = get_logger(__name__)


def _hash_content(text: str | None, doc_type: str | None) -> str | None:
    if not text:
        return None
    content = f"{text}{doc_type or ''}"
    return hashlib.sha256(content.encode()).hexdigest()


async def migrate() -> None:
    async with db_session() as db:
        documents = await db.documents.find().to_list(length=None)
        logger.info(f"Found {len(documents)} documents to migrate")

        for doc in documents:
            document_id = doc.get("id")
            product_id = doc.get("product_id")
            if not document_id or not product_id:
                continue

            content_hash = _hash_content(doc.get("text"), doc.get("doc_type"))

            version = DocumentVersion(
                document_id=document_id,
                product_id=product_id,
                url=doc.get("url"),
                canonical_url=doc.get("url"),
                title=doc.get("title"),
                doc_type=doc.get("doc_type") or "other",
                locale=doc.get("locale"),
                regions=doc.get("regions") or [],
                effective_date=doc.get("effective_date"),
                markdown=doc.get("markdown"),
                text=doc.get("text"),
                content_hash=content_hash,
                metadata=doc.get("metadata") or {},
                created_at=doc.get("created_at") or datetime.now(),
            )

            await db.document_versions.insert_one(version.model_dump())

            text = doc.get("text") or ""
            if text:
                section = DocumentSection(
                    document_id=document_id,
                    version_id=version.id,
                    title=doc.get("title"),
                    level=1,
                    order=0,
                    start_char=0,
                    end_char=len(text),
                    text=text,
                )
                await db.document_sections.insert_one(section.model_dump())

        logger.info("Migration completed")


if __name__ == "__main__":
    asyncio.run(migrate())
