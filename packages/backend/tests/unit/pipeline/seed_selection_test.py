"""Seed selection prefers domain roots and appends optional override seeds."""

from unittest.mock import AsyncMock

import pytest

from src.models.product import Product
from src.pipeline import PolicyDocumentPipeline


def _pipeline() -> PolicyDocumentPipeline:
    return PolicyDocumentPipeline()


def test_domain_roots_are_primary_with_overrides_appended() -> None:
    product = Product(
        id="p1",
        name="Acme",
        slug="acme",
        domains=["acme.com"],
        crawl_base_urls=["https://acme.com/privacy", "https://legal.acme.com/policies"],
    )
    urls = _pipeline()._get_crawl_urls(product)
    assert urls == [
        "https://acme.com",
        "https://acme.com/privacy",
        "https://legal.acme.com/policies",
    ]


def test_root_override_is_deduped_against_domain_root() -> None:
    product = Product(
        id="p2",
        name="Acme",
        slug="acme",
        domains=["acme.com"],
        crawl_base_urls=["https://acme.com/", "https://acme.com"],
    )
    urls = _pipeline()._get_crawl_urls(product)
    assert urls == ["https://acme.com"]


def test_overrides_still_work_without_domains() -> None:
    product = Product(
        id="p3",
        name="Acme",
        slug="acme",
        domains=[],
        crawl_base_urls=["legal.acme.com/privacy", "https://help.acme.com/terms"],
    )
    urls = _pipeline()._get_crawl_urls(product)
    assert urls == [
        "https://legal.acme.com/privacy",
        "https://help.acme.com/terms",
    ]


# ---------------------------------------------------------------------------
# Extension footer seeds
# ---------------------------------------------------------------------------


def test_extension_seeds_appear_in_crawl_urls() -> None:
    """seed_urls injected via _process_product must appear in the crawl URL list."""
    product = Product(
        id="p4",
        name="Shein",
        slug="shein",
        domains=["shein.com"],
        crawl_base_urls=[],
    )
    seed = "https://fr.shein.com/Consumer-Privacy-Notice-s-101.html"
    augmented = product.model_copy(
        update={"crawl_base_urls": list(product.crawl_base_urls or []) + [seed]}
    )
    urls = _pipeline()._get_crawl_urls(augmented)
    assert seed in urls


def test_extension_seed_domain_added_to_allowed_domains() -> None:
    """A seed from a different subdomain expands the crawler's allowed-domain list."""
    product = Product(
        id="p5",
        name="Shein",
        slug="shein",
        domains=["shein.com"],
        crawl_base_urls=[],
    )
    seed = "https://fr.shein.com/Consumer-Privacy-Notice-s-101.html"
    augmented = product.model_copy(
        update={"crawl_base_urls": list(product.crawl_base_urls or []) + [seed]}
    )
    allowed = PolicyDocumentPipeline._allowed_domains_for_product(augmented)
    assert any("shein" in d for d in allowed)


@pytest.mark.asyncio
async def test_extension_seeds_reach_crawl_multiple(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seeds persisted into product.crawl_base_urls reach crawl_multiple naturally.

    The extension writes seeds to the product in the DB before the pipeline runs.
    The pipeline fetches the updated product and _get_crawl_urls includes the seeds
    without any special parameter threading.
    """
    seed = "https://fr.shein.com/Consumer-Privacy-Notice-s-101.html"
    product = Product(
        id="p6",
        name="Shein",
        slug="shein",
        domains=["shein.com"],
        crawl_base_urls=[seed],  # seeds already persisted to the product
    )
    batches: list[list[str]] = []

    class _FakeCrawler:
        def __init__(self, result_callback=None, **_kwargs):
            self._result_callback = result_callback

        async def crawl_multiple(self, urls: list[str]) -> list:
            batches.append(list(urls))
            return []

    pipeline = _pipeline()
    monkeypatch.setattr(
        pipeline, "_create_crawler_for_product", lambda _p, **kw: _FakeCrawler(**kw)
    )
    monkeypatch.setattr(pipeline, "_start_crawl_session", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "_finish_crawl_session", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "_get_recently_stored_urls", AsyncMock(return_value=[]))

    await pipeline._process_product(product)

    all_crawled = [url for batch in batches for url in batch]
    assert seed in all_crawled


def test_product_seed_overrides_merge_for_known_slug() -> None:
    product = Product(
        id="p7",
        name="Facebook",
        slug="facebook",
        domains=["facebook.com"],
        crawl_base_urls=[],
    )
    urls = _pipeline()._get_crawl_urls(product)
    assert urls == [
        "https://facebook.com",
        "https://mbasic.facebook.com/legal/terms/plain_text_terms",
        "https://mbasic.facebook.com/privacy/policies/cookies/printable",
        "https://mbasic.facebook.com/privacy/policy/printable/version/25862970456621906",
    ]


def test_openai_policies_hub_seed_override() -> None:
    product = Product(
        id="p8",
        name="OpenAI",
        slug="openai",
        domains=["openai.com"],
        crawl_base_urls=[],
    )
    urls = _pipeline()._get_crawl_urls(product)
    assert urls == [
        "https://openai.com",
        "https://openai.com/policies",
    ]
