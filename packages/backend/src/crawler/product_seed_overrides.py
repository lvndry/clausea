"""Known policy-page seeds for products where discovery from the domain root fails.

Merged into every crawl for the matching product slug (in addition to DB
``crawl_base_urls``). Use mbasic/lightweight URLs for sites behind anti-bot walls.
"""

from __future__ import annotations

PRODUCT_CRAWL_SEED_OVERRIDES: dict[str, list[str]] = {
    "facebook": [
        "https://mbasic.facebook.com/legal/terms/plain_text_terms/",
        "https://mbasic.facebook.com/privacy/policies/cookies/printable/",
        "https://mbasic.facebook.com/privacy/policy/printable/version/25862970456621906/",
    ],
    "openai": [
        "https://openai.com/policies/",
    ],
}


def crawl_seed_overrides_for_slug(slug: str) -> list[str]:
    return list(PRODUCT_CRAWL_SEED_OVERRIDES.get(slug, []))
