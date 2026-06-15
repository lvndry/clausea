"""A robots.txt block must be recorded as a robots_txt_blocked crawl error, so the
pipeline can tell the user the SITE refused us (not that we failed). Without this, a
robots-blocked crawl reports the generic "no documents found".
"""

import pytest

from src.crawler import CrawlResult
from src.models.product import Product
from src.pipeline import PolicyDocumentPipeline


def _product() -> Product:
    return Product(
        id="p1", name="X", slug="x", domains=["x.com"], crawl_base_urls=["https://x.com"]
    )


@pytest.mark.asyncio
async def test_robots_block_recorded_as_robots_txt_blocked_crawl_error() -> None:
    pipeline = PolicyDocumentPipeline()
    blocked = CrawlResult(
        url="https://x.com/legal",
        title="",
        content="",
        markdown="",
        metadata={},
        status_code=403,
        success=False,
        error_message="Blocked by robots.txt: Blocked by pattern: /",
    )

    docs = await pipeline._classify_results([blocked], _product(), set(), set())

    assert docs == []
    assert len(pipeline.stats.crawl_errors) == 1
    assert pipeline.stats.crawl_errors[0]["error_type"] == "robots_txt_blocked"
