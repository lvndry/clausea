"""Rules for when a product needs a full crawl vs analysis-only requeue."""

from __future__ import annotations

from motor.core import AgnosticDatabase


async def has_overview(db: AgnosticDatabase, slug: str) -> bool:
    row = await db.product_intelligence.find_one(
        {"product_slug": slug, "overview": {"$exists": True, "$ne": None}},
        {"_id": 1},
    )
    return row is not None


async def count_policy_documents(db: AgnosticDatabase, *, slug: str, product_id: str | None) -> int:
    clauses: list[dict] = [{"product_slug": slug}]
    if product_id:
        clauses.append({"product_id": product_id})
    return await db.documents.count_documents({"$or": clauses, "doc_type": {"$ne": "other"}})


async def product_needs_full_crawl(
    db: AgnosticDatabase, *, slug: str, product_id: str | None
) -> bool:
    """True only when there are no stored policy documents to analyze."""
    return await count_policy_documents(db, slug=slug, product_id=product_id) == 0
