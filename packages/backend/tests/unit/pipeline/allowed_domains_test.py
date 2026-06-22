"""A crawl seed on a different registered domain must be added to allowed_domains, or the
domain gate rejects it and a whole policy source (e.g. shein's corporate site) is dropped."""

from src.models.product import Product
from src.pipeline import PolicyDocumentPipeline

_fn = PolicyDocumentPipeline._allowed_domains_for_product


def test_seed_on_other_registered_domain_is_unioned() -> None:
    product = Product(
        id="p1",
        slug="shein",
        name="Shein",
        domains=["shein.com"],
        crawl_base_urls=[
            "https://m.shein.com/us/PRIVACY-POLICY-a-1061.html",
            "https://www.sheingroup.com/privacy-policy",
        ],
    )
    allowed = _fn(product)
    assert set(allowed) == {"shein.com", "sheingroup.com"}


def test_same_domain_seeds_do_not_duplicate() -> None:
    product = Product(
        id="p2",
        slug="x",
        name="X",
        domains=["shein.com"],
        crawl_base_urls=["https://m.shein.com/a", "https://us.shein.com/b"],
    )
    allowed = _fn(product)
    assert allowed == ["shein.com"]


def test_empty_seeds_returns_product_domains() -> None:
    product = Product(id="p3", slug="x", name="X", domains=["acme.com"], crawl_base_urls=[])
    assert _fn(product) == ["acme.com"]
