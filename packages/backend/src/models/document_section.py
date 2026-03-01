from __future__ import annotations

from datetime import datetime

import shortuuid
from pydantic import BaseModel, Field


class DocumentSection(BaseModel):
    """Structured section of a document for evidence anchoring."""

    id: str = Field(default_factory=shortuuid.uuid)
    document_id: str
    version_id: str
    title: str | None = None
    level: int | None = None
    order: int = 0
    start_char: int | None = None
    end_char: int | None = None
    text: str
    created_at: datetime = Field(default_factory=datetime.now)
