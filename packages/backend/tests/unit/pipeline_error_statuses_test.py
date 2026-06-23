"""Tests for the granular pipeline error statuses added in feat/pipeline-error-statuses.

Covers:
- site_unavailable: all crawl errors are connection-level (DNS/SSL/timeout/network)
- access_denied:    all crawl errors are hard HTTP/anti-bot blocks
- no_policy_found:  pages were fetched OK but rejected by content filters
- analysis_failed:  synthesise or generate_overview threw an unexpected exception
"""

from contextlib import ExitStack, asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

from src.analyser import AnalysisResult
from src.models.document import Document
from src.models.pipeline_job import PipelineErrorCode, PipelineJob
from src.repositories.pipeline_repository import PipelineRepository
from src.services.pipeline_service import PipelineService


@pytest.fixture
def mock_db():
    return MagicMock()


def _make_job(job_id: str = "job-test") -> PipelineJob:
    return PipelineJob(
        id=job_id,
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="pending",
    )


def _make_service(job: PipelineJob) -> PipelineService:
    repo = MagicMock(spec=PipelineRepository)
    repo.find_by_id = AsyncMock(return_value=job)
    repo.update = AsyncMock()
    repo.update_fields = AsyncMock()
    return PipelineService(pipeline_repo=repo)


def _make_product_svc() -> MagicMock:
    product = SimpleNamespace(id="test-product-id", slug="test-product", name="Test Product")
    svc = MagicMock()
    svc.get_product_by_slug = AsyncMock(return_value=product)
    return svc


def _make_empty_doc_svc() -> MagicMock:
    svc = MagicMock()
    svc.get_product_documents_by_slug = AsyncMock(return_value=[])
    return svc


def _patches(mock_db, fake_pipeline, product_svc, doc_svc=None) -> ExitStack:
    """Return an ExitStack with the common pipeline service patches already entered."""

    @asynccontextmanager
    async def fake_db_session():
        yield mock_db

    if doc_svc is None:
        doc_svc = _make_empty_doc_svc()

    stack = ExitStack()
    stack.enter_context(patch("src.services.pipeline_service.db_session", fake_db_session))
    stack.enter_context(
        patch("src.services.pipeline_service.create_product_service", return_value=product_svc)
    )
    stack.enter_context(
        patch("src.services.pipeline_service.create_document_service", return_value=doc_svc)
    )
    stack.enter_context(
        patch("src.services.pipeline_service.PolicyDocumentPipeline", return_value=fake_pipeline)
    )
    return stack


# ---------------------------------------------------------------------------
# site_unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_site_unavailable_when_all_errors_are_connection_level(mock_db):
    """When every crawl error is network/timeout type the job must become site_unavailable.

    This is distinct from ``no_documents`` (unknown reason) and from ``failed``
    (retriable interruption). The site is unreachable — the user sees a targeted
    "site may be down" message rather than a generic failure.
    """
    job = _make_job("job-unavail")
    service = _make_service(job)
    product_svc = _make_product_svc()

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[
            {
                "url": "https://test.com/",
                "status_code": 0,
                "error_message": "Cannot connect to host test.com:443 [connection refused]",
                "error_type": "network_error",
            },
            {
                "url": "https://test.com/privacy",
                "status_code": 0,
                "error_message": "getaddrinfo failed: DNS lookup failed for test.com",
                "error_type": "network_error",
            },
        ],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    with _patches(mock_db, fake_pipeline, product_svc):
        await service.run_pipeline("job-unavail")

    assert job.status == "site_unavailable"
    assert job.error == PipelineErrorCode.site_unavailable
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_site_unavailable_includes_timeout_errors(mock_db):
    """Timeout errors are treated as connection-level for site_unavailable detection."""
    job = _make_job("job-timeout")
    service = _make_service(job)
    product_svc = _make_product_svc()

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[
            {
                "url": "https://test.com/",
                "status_code": 0,
                "error_message": "Connection timed out",
                "error_type": "timeout",
            },
        ],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    with _patches(mock_db, fake_pipeline, product_svc):
        await service.run_pipeline("job-timeout")

    assert job.status == "site_unavailable"
    assert job.error == PipelineErrorCode.site_unavailable


# ---------------------------------------------------------------------------
# access_denied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_denied_when_all_errors_are_hard_http_403(mock_db):
    """When every crawl error is a hard 4xx block the job must become access_denied.

    Distinct from robots_blocked (robots.txt) and site_unavailable (connection).
    """
    job = _make_job("job-403")
    service = _make_service(job)
    product_svc = _make_product_svc()

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[
            {
                "url": "https://test.com/",
                "status_code": 403,
                "error_message": "HTTP 403 Forbidden",
                "error_type": "http_error",
            },
            {
                "url": "https://test.com/privacy",
                "status_code": 403,
                "error_message": "HTTP 403 Forbidden",
                "error_type": "http_error",
            },
        ],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    with _patches(mock_db, fake_pipeline, product_svc):
        await service.run_pipeline("job-403")

    assert job.status == "access_denied"
    assert job.error == PipelineErrorCode.access_denied
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_access_denied_when_bot_detection_keywords_in_error(mock_db):
    """Bot-detection keywords in the error message trigger access_denied."""
    job = _make_job("job-bot")
    service = _make_service(job)
    product_svc = _make_product_svc()

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[
            {
                "url": "https://test.com/",
                "status_code": 200,
                "error_message": "Cloudflare challenge page detected",
                "error_type": "http_error",
            },
        ],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    with _patches(mock_db, fake_pipeline, product_svc):
        await service.run_pipeline("job-bot")

    assert job.status == "access_denied"
    assert job.error == PipelineErrorCode.access_denied


# ---------------------------------------------------------------------------
# no_policy_found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_policy_found_when_pages_fetched_but_rejected(mock_db):
    """When crawl_skip_reasons are present the job must become no_policy_found.

    This is distinct from ``no_documents`` (0 pages crawled) — here the crawler
    DID fetch pages but the classifier found nothing relevant.
    """
    job = _make_job("job-nopolicy")
    service = _make_service(job)
    product_svc = _make_product_svc()

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[],
        crawl_skip_reasons=[
            {"url": "https://test.com/about", "reason": "low_legal_score", "detail": "score=0.12"},
            {"url": "https://test.com/faq", "reason": "non_policy_classification", "detail": None},
        ],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    with _patches(mock_db, fake_pipeline, product_svc):
        await service.run_pipeline("job-nopolicy")

    assert job.status == "no_policy_found"
    assert job.error == PipelineErrorCode.no_policy_found
    assert job.completed_at is not None
    assert "low_legal_score" in (job.error_detail or "")


# ---------------------------------------------------------------------------
# analysis_failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analysis_failed_when_synthesise_raises(mock_db):
    """If analyse_product_documents raises unexpectedly the job must become analysis_failed.

    Unlike the ``all_analysis_failed`` / ``core_docs_unanalyzed`` codes (where the
    analyser returned but no docs were successfully analysed), this covers the case
    where the function itself throws — e.g. an unexpected LLM SDK error.
    """
    job = _make_job("job-synth-raise")
    service = _make_service(job)
    product_svc = _make_product_svc()
    product_svc.get_product_overview_data = AsyncMock(return_value={"overview": {"summary": "ok"}})

    crawl_stats = SimpleNamespace(
        total_documents_found=2,
        policy_documents_stored=2,
        crawl_errors=[],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    doc_svc = MagicMock()
    doc_svc.get_product_documents_by_slug = AsyncMock(return_value=[])

    analyse_mock = AsyncMock(side_effect=RuntimeError("Unexpected LLM SDK error"))
    overview_mock = AsyncMock()

    @asynccontextmanager
    async def fake_db_session():
        yield mock_db

    with (
        patch("src.services.pipeline_service.db_session", fake_db_session),
        patch("src.services.pipeline_service.create_product_service", return_value=product_svc),
        patch("src.services.pipeline_service.create_document_service", return_value=doc_svc),
        patch("src.services.pipeline_service.PolicyDocumentPipeline", return_value=fake_pipeline),
        patch("src.services.pipeline_service.analyse_product_documents", analyse_mock),
        patch("src.services.pipeline_service.generate_product_overview", overview_mock),
    ):
        await service.run_pipeline("job-synth-raise")

    assert job.status == "analysis_failed"
    assert job.error == PipelineErrorCode.analysis_failed
    assert job.completed_at is not None
    assert "Unexpected LLM SDK error" in (job.error_detail or "")
    overview_mock.assert_not_called()


@pytest.mark.asyncio
async def test_analysis_failed_when_overview_raises(mock_db):
    """If generate_product_overview raises unexpectedly the job must become analysis_failed.

    The synthesise step succeeded (documents were analysed), but the overview
    generation threw. The user is offered a "try again" path since this is transient.
    """
    job = _make_job("job-overview-raise")
    service = _make_service(job)
    product_svc = _make_product_svc()

    crawl_stats = SimpleNamespace(
        total_documents_found=1,
        policy_documents_stored=1,
        crawl_errors=[],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    doc_svc = MagicMock()
    doc_svc.get_product_documents_by_slug = AsyncMock(return_value=[])

    analysed_doc = create_autospec(Document, instance=True)
    analysed_doc.analysis = object()
    analysed_doc.doc_type = "privacy_policy"
    analysed_docs = [analysed_doc]
    analyse_mock = AsyncMock(
        return_value=AnalysisResult(documents=analysed_docs, analyses_skipped=0)
    )
    overview_mock = AsyncMock(side_effect=RuntimeError("Overview LLM timed out"))

    @asynccontextmanager
    async def fake_db_session():
        yield mock_db

    with (
        patch("src.services.pipeline_service.db_session", fake_db_session),
        patch("src.services.pipeline_service.create_product_service", return_value=product_svc),
        patch("src.services.pipeline_service.create_document_service", return_value=doc_svc),
        patch("src.services.pipeline_service.PolicyDocumentPipeline", return_value=fake_pipeline),
        patch("src.services.pipeline_service.analyse_product_documents", analyse_mock),
        patch("src.services.pipeline_service.generate_product_overview", overview_mock),
    ):
        await service.run_pipeline("job-overview-raise")

    assert job.status == "analysis_failed"
    assert job.error == PipelineErrorCode.analysis_failed
    assert job.completed_at is not None
    assert "Overview LLM timed out" in (job.error_detail or "")


# ---------------------------------------------------------------------------
# Regression: no_documents still used for truly unknown cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_documents_used_when_no_errors_and_no_skips(mock_db):
    """When the crawl stores 0 docs with no errors and no skip reasons, use no_documents.

    This preserves backward compatibility for the "queue was empty / site had no
    pages" case where we have no signal about WHY the crawl found nothing.
    """
    job = _make_job("job-unknown")
    service = _make_service(job)
    product_svc = _make_product_svc()

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    with _patches(mock_db, fake_pipeline, product_svc):
        await service.run_pipeline("job-unknown")

    assert job.status == "no_documents"
    assert job.completed_at is not None


# ---------------------------------------------------------------------------
# robots_blocked still works (regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_robots_blocked_when_all_errors_are_robots_txt(mock_db):
    """Regression: all-robots-blocked crawl still produces robots_blocked status."""
    job = _make_job("job-robots")
    service = _make_service(job)
    product_svc = _make_product_svc()

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[
            {
                "url": "https://test.com/",
                "status_code": 403,
                "error_message": "Blocked by robots.txt: Disallow: /",
                "error_type": "robots_txt_blocked",
            },
        ],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    with _patches(mock_db, fake_pipeline, product_svc):
        await service.run_pipeline("job-robots")

    assert job.status == "robots_blocked"
    assert job.error == PipelineErrorCode.crawl_robots_blocked
    assert job.completed_at is not None
