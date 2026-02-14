from pydantic import BaseModel, Field

from src.models.user import UserTier


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
    visible_to_tiers: list[UserTier] = Field(
        default_factory=lambda: [UserTier.FREE, UserTier.BUSINESS, UserTier.ENTERPRISE]
    )
