from datetime import datetime

from pydantic import BaseModel, Field

from src.models.user import UserTier


class ProductStats(BaseModel):
    """Denormalized product stats for list/extension queries."""

    document_count: int = 0
    grade: str | None = None
    has_overview: bool = False
    last_indexed_at: datetime | None = None


# Provenance of ``Product.name``. Controls whether the pipeline is allowed to
# overwrite the name with a brand extracted from crawled page metadata.
#   - "manual":          set by a human via the dashboard -> never overwritten.
#   - "auto_domain":     derived from the domain at extension/pipeline creation
#                        (e.g. "Netflix" from netflix.com) -> pipeline may improve it.
#   - "auto_extracted":  already improved by the pipeline from metadata -> frozen.
#   - None:              legacy products created before this field existed.
NAME_SOURCE_MANUAL = "manual"
NAME_SOURCE_AUTO_DOMAIN = "auto_domain"
NAME_SOURCE_AUTO_EXTRACTED = "auto_extracted"


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
    crawl_denied_domains: list[str] = Field(default_factory=list)
    crawl_ignore_robots: bool = False
    logo: str | None = None
    visible_to_tiers: list[UserTier] = Field(default_factory=lambda: [UserTier.FREE, UserTier.PRO])
    stats: ProductStats = Field(default_factory=ProductStats)
    thin_evidence: bool = False
    thin_evidence_reason: str | None = None
    name_source: str | None = None
