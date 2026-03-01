from __future__ import annotations

from datetime import datetime
from typing import Any

import shortuuid
from pydantic import BaseModel, Field

from src.models.document import DocType, Region


class DocumentVersion(BaseModel):
    """Immutable snapshot of a document at a point in time."""

    id: str = Field(default_factory=shortuuid.uuid)
    document_id: str
    product_id: str
    url: str
    canonical_url: str | None = None
    source_session_id: str | None = None
    title: str | None = None
    doc_type: DocType = "other"
    locale: str | None = None
    regions: list[Region] = Field(default_factory=list)
    effective_date: datetime | None = None
    raw_html: str | None = None
    markdown: str | None = None
    text: str | None = None
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
