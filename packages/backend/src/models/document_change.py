"""Slim document change records (hash/metadata only — no markdown copies)."""

from __future__ import annotations

from datetime import datetime

import shortuuid
from pydantic import BaseModel, Field


class DocumentChange(BaseModel):
    """Records a document content change without archiving full text."""

    id: str = Field(default_factory=shortuuid.uuid)
    document_id: str
    product_id: str
    product_slug: str | None = None
    content_hash: str
    previous_hash: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    job_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
