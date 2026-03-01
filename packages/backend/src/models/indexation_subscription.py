"""Indexation subscription model.

Stores user emails to notify when a product finishes indexation (pipeline completed).
"""

from __future__ import annotations

from datetime import datetime

import shortuuid
from pydantic import BaseModel, EmailStr, Field


class IndexationSubscription(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    product_slug: str
    email: EmailStr
    created_at: datetime = Field(default_factory=datetime.now)
    notified_at: datetime | None = None
