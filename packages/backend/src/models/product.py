from datetime import datetime

from pydantic import BaseModel, Field

from src.models.user import UserTier


class ProductStats(BaseModel):
    """Denormalized product stats for list/extension queries."""

    document_count: int = 0
    risk_score: int | None = None
    has_overview: bool = False
    last_indexed_at: datetime | None = None


class Product(BaseModel):
    id: str
    name: str
    company_name: str | None = None
    description: str | None = None
    slug: str
    domains: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    crawl_base_urls: list[str] = Field(default_factory=list)
    crawl_allowed_paths: list[str] = Field(default_factory=list)
    crawl_denied_paths: list[str] = Field(default_factory=list)
    logo: str | None = None
    visible_to_tiers: list[UserTier] = Field(default_factory=lambda: [UserTier.FREE, UserTier.PRO])
    stats: ProductStats = Field(default_factory=ProductStats)
