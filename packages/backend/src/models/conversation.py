from datetime import datetime
from typing import Literal

import shortuuid
from pydantic import BaseModel, Field


class Message(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class Conversation(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    user_id: str
    product_name: str
    product_slug: str
    company_name: str | None = None
    product_description: str | None = None

    # Optional metadata for UX/filters
    title: str | None = None
    archived: bool = False
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)

    # Content and counters
    documents: list[str] = Field(default_factory=list)  # List of document IDs
    messages: list[Message] = Field(default_factory=list)
    message_count: int = 0
    last_message_at: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
