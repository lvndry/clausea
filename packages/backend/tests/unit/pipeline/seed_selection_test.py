"""Seed selection prefers domain roots and appends optional override seeds."""

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
