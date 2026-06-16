"""_process_product stores documents incrementally as the crawl produces them.

A multi-hour crawl killed at the time ceiling must keep the work already done, so each
crawled result is classified and stored inside the crawler's per-result callback rather
than in one end-of-crawl batch. This test drives _process_product with a fake crawler that
fires the registered callback per result, and asserts:
  - _store_documents is invoked as results arrive (interleaved with the crawl), not once;
  - the streamed documents drive the _should_fallback_crawl decision;
  - policy_documents_stored is counted once (no redundant final batch store).
"""

from unittest.mock import AsyncMock

import pytest

from src.crawler import CrawlResult
from src.models.document import DocType, Document
from src.models.product import Product
from src.pipeline import PolicyDocumentPipeline


def _result(url: str) -> CrawlResult:
    # Distinct content per URL so the near-duplicate fingerprint filter in
    # _classify_results keeps each page (real policy pages have different text).
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
        text="t" * 400,
        markdown="t",
    )


class _FakeCrawler:
    """Stands in for ClauseaCrawler: replays canned results through the result_callback."""

    def __init__(self, results: list[CrawlResult], result_callback) -> None:
        self._results = results
        self._result_callback = result_callback

    async def crawl_multiple(self, _urls: list[str]) -> list[CrawlResult]:
        for result in self._results:
            if self._result_callback is not None:
                await self._result_callback(result)
        return list(self._results)


@pytest.mark.asyncio
async def test_streams_store_per_result_and_counts_once(monkeypatch):
    product = Product(
        id="prod-1",
        name="Acme",
        slug="acme",
        domains=["acme.com"],
        crawl_base_urls=["https://acme.com/"],
    )

    discovery = [_result("https://acme.com/privacy"), _result("https://acme.com/terms")]

    # Record the order of classify vs store calls to prove interleaving (not one batch).
    call_log: list[str] = []

    async def fake_process_crawl_result(result: CrawlResult, _product):
        call_log.append(f"classify:{result.url}")
        doc_type = "privacy_policy" if "privacy" in result.url else "terms_of_service"
        return _doc(result.url, doc_type)

    stored: list[str] = []

    async def fake_store_documents(documents):
        for document in documents:
            call_log.append(f"store:{document.url}")
            stored.append(document.url)
        return len(documents)

    pipeline = PolicyDocumentPipeline(
        min_docs_before_fallback=1,
        required_doc_types=["privacy_policy", "terms_of_service"],
    )

    monkeypatch.setattr(pipeline, "_process_crawl_result", fake_process_crawl_result)
    monkeypatch.setattr(pipeline, "_store_documents", AsyncMock(side_effect=fake_store_documents))
    monkeypatch.setattr(pipeline, "_start_crawl_session", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "_finish_crawl_session", AsyncMock(return_value=None))

    def fake_create_crawler(_product, **kwargs):
        return _FakeCrawler(discovery, kwargs.get("result_callback"))

    monkeypatch.setattr(pipeline, "_create_crawler_for_product", fake_create_crawler)

    documents = await pipeline._process_product(product)

    # Storage interleaved with classification, one store per result as it arrived.
    assert call_log == [
        "classify:https://acme.com/privacy",
        "store:https://acme.com/privacy",
        "classify:https://acme.com/terms",
        "store:https://acme.com/terms",
    ]
    # Both doc types present -> coverage satisfied -> no fallback crawl ran.
    assert {document.url for document in documents} == {
        "https://acme.com/privacy",
        "https://acme.com/terms",
    }
    # Counted once: two stored, no redundant end-of-crawl batch store.
    assert pipeline.stats.policy_documents_stored == 2
    assert stored == ["https://acme.com/privacy", "https://acme.com/terms"]


@pytest.mark.asyncio
async def test_streamed_docs_drive_fallback_decision(monkeypatch):
    product = Product(
        id="prod-1",
        name="Acme",
        slug="acme",
        domains=["acme.com"],
        crawl_base_urls=["https://acme.com/"],
    )

    # Discovery yields only a privacy policy; required types include terms -> fallback fires.
    discovery = [_result("https://acme.com/privacy")]
    fallback = [_result("https://acme.com/terms")]
    passes = iter([discovery, fallback])

    async def fake_process_crawl_result(result: CrawlResult, _product):
        doc_type = "privacy_policy" if "privacy" in result.url else "terms_of_service"
        return _doc(result.url, doc_type)

    pipeline = PolicyDocumentPipeline(
        min_docs_before_fallback=1,
        required_doc_types=["privacy_policy", "terms_of_service"],
    )

    store_mock = AsyncMock(side_effect=lambda documents: len(documents))
    monkeypatch.setattr(pipeline, "_process_crawl_result", fake_process_crawl_result)
    monkeypatch.setattr(pipeline, "_store_documents", store_mock)
    monkeypatch.setattr(pipeline, "_start_crawl_session", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "_finish_crawl_session", AsyncMock(return_value=None))

    crawlers_created: list[_FakeCrawler] = []

    def fake_create_crawler(_product, **kwargs):
        crawler = _FakeCrawler(next(passes), kwargs.get("result_callback"))
        crawlers_created.append(crawler)
        return crawler

    monkeypatch.setattr(pipeline, "_create_crawler_for_product", fake_create_crawler)

    documents = await pipeline._process_product(product)

    # The fallback pass ran because the discovery-streamed docs lacked terms_of_service.
    assert len(crawlers_created) == 2
    assert {document.doc_type for document in documents} == {
        "privacy_policy",
        "terms_of_service",
    }
    assert pipeline.stats.policy_documents_stored == 2
