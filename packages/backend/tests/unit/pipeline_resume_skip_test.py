"""_process_product wires recently stored URLs into the crawler for resume.

A crawl interrupted and retried minutes/hours later must skip re-fetching the docs it
already stored, instead of re-rendering hours of work. _process_product queries the
product's recently stored docs (within RESUME_FRESH_HOURS) and passes their URLs to
every crawler it creates via recently_stored_urls. Docs stored long ago are excluded by
the cutoff, so scheduled monitoring re-crawls days later still re-fetch and detect change.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src import pipeline as pipeline_module
from src.crawler import CrawlResult
from src.models.document import DocType, Document
from src.models.product import Product
from src.pipeline import PolicyDocumentPipeline


def _result(url: str) -> CrawlResult:
    return CrawlResult(
        url=url,
        title="",
        content=f"unique content for {url} " * 30,
        markdown="x",
        metadata={},
        status_code=200,
        success=True,
    )


def _doc(url: str, doc_type: DocType) -> Document:
    return Document(
        id=url,
        url=url,
        product_id="prod-1",
        doc_type=doc_type,
        title="T",
        markdown="t",
    )


class _FakeCrawler:
    def __init__(self, results, result_callback) -> None:
        self._results = results
        self._result_callback = result_callback

    async def crawl_multiple(self, _urls):
        for result in self._results:
            if self._result_callback is not None:
                await self._result_callback(result)
        return list(self._results)


def _make_product() -> Product:
    return Product(
        id="prod-1",
        name="Acme",
        slug="acme",
        domains=["acme.com"],
        crawl_base_urls=["https://acme.com/"],
    )


@pytest.mark.asyncio
async def test_recent_urls_passed_to_crawler_as_skips(monkeypatch):
    product = _make_product()
    discovery = [_result("https://acme.com/privacy"), _result("https://acme.com/terms")]

    async def fake_process_crawl_result(result: CrawlResult, _product):
        doc_type = "privacy_policy" if "privacy" in result.url else "terms_of_service"
        return _doc(result.url, doc_type)

    pipeline = PolicyDocumentPipeline(
        min_docs_before_fallback=1,
        required_doc_types=["privacy_policy", "terms_of_service"],
    )

    monkeypatch.setattr(pipeline, "_process_crawl_result", fake_process_crawl_result)
    monkeypatch.setattr(pipeline, "_store_documents", AsyncMock(side_effect=lambda docs: len(docs)))
    monkeypatch.setattr(pipeline, "_start_crawl_session", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "_finish_crawl_session", AsyncMock(return_value=None))

    # Stand in for the DB query: only the recent doc's URL is returned (stale ones are
    # already excluded by the repository's cutoff query, tested separately).
    recent_urls = ["https://acme.com/privacy"]
    monkeypatch.setattr(
        pipeline,
        "_get_recently_stored_urls",
        AsyncMock(return_value=recent_urls),
    )

    captured_skips: list[list[str] | None] = []

    def fake_create_crawler(_product, **kwargs):
        captured_skips.append(kwargs.get("recently_stored_urls"))
        return _FakeCrawler(discovery, kwargs.get("result_callback"))

    monkeypatch.setattr(pipeline, "_create_crawler_for_product", fake_create_crawler)

    await pipeline._process_product(product)

    # The discovery crawler received exactly the recent URLs as its resume skip-set.
    assert captured_skips
    assert captured_skips[0] == recent_urls


@pytest.mark.asyncio
async def test_get_recently_stored_urls_queries_with_freshness_cutoff(monkeypatch):
    product = _make_product()
    pipeline = PolicyDocumentPipeline()

    captured_product_id: list[str] = []
    captured_cutoff: list[datetime] = []

    class _FakeService:
        async def get_recent_document_urls(self, _db, product_id: str, cutoff: datetime):
            captured_product_id.append(product_id)
            captured_cutoff.append(cutoff)
            # Service returns only docs already filtered to the recent window.
            return ["https://acme.com/privacy"]

    class _FakeDbCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(pipeline_module.pipeline, "db_session", lambda: _FakeDbCtx())
    monkeypatch.setattr(pipeline_module.pipeline, "create_document_service", lambda: _FakeService())

    before = datetime.now() - timedelta(hours=pipeline_module.RESUME_FRESH_HOURS)
    urls = await pipeline._get_recently_stored_urls(product)
    after = datetime.now() - timedelta(hours=pipeline_module.RESUME_FRESH_HOURS)

    assert urls == ["https://acme.com/privacy"]
    assert captured_product_id == ["prod-1"]
    # Cutoff is "now minus the freshness window", so it falls between the two samples.
    assert before <= captured_cutoff[0] <= after


@pytest.mark.asyncio
async def test_query_failure_disables_skip_but_does_not_crash(monkeypatch):
    product = _make_product()
    pipeline = PolicyDocumentPipeline()

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(pipeline_module.pipeline, "db_session", lambda: _boom())

    urls = await pipeline._get_recently_stored_urls(product)
    assert urls == []
