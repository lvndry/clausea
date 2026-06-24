import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.analyser import AnalysisResult
from src.models.pipeline_job import PipelineErrorCode, PipelineJob, PipelineStep
from src.repositories.pipeline_repository import PipelineRepository
from src.services import pipeline_service as ps
from src.services.pipeline_service import PipelineService


@pytest.fixture
def mock_repo():
    repo = MagicMock(spec=PipelineRepository)
    repo.update_fields = AsyncMock()
    repo.find_by_id = AsyncMock()
    return repo


@pytest.fixture
def pipeline_service(mock_repo):
    return PipelineService(pipeline_repo=mock_repo)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.mark.asyncio
async def test_update_step_clears_progress_on_completion(pipeline_service, mock_repo, mock_db):
    # Setup: Job in running state with some progress
    job = PipelineJob(
        id="job-123",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="crawling",
        steps=[
            PipelineStep(
                name="crawling",
                status="running",
                progress_current=50,
                progress_total=100,
                progress_percent=50.0,
            )
        ],
    )

    # Action: Mark step as completed
    await pipeline_service._update_step(mock_db, job, "crawling", "completed", "Done!")

    # Verify: Repository updated with correct fields
    mock_repo.update_fields.assert_called_once()
    args = mock_repo.update_fields.call_args[0][2]

    assert args["steps.0.status"] == "completed"
    assert args["steps.0.message"] == "Done!"
    # Progress fields MUST be cleared
    assert args["steps.0.progress_current"] is None
    assert args["steps.0.progress_total"] is None
    assert args["steps.0.progress_percent"] is None

    # Verify local object updated too
    assert job.steps[0].status == "completed"
    assert job.steps[0].progress_current is None


@pytest.mark.asyncio
async def test_update_step_progress_skips_terminal_steps(pipeline_service, mock_repo, mock_db):
    # Setup: Job step is already completed
    job = PipelineJob(
        id="job-123",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="synthesising",
        steps=[PipelineStep(name="crawling", status="completed", message="Final Message")],
    )

    # Action: Call progress update (simulating a late-running background task)
    await pipeline_service._update_step_progress(
        mock_db, job, "crawling", current=10, total=10, message="Stale Progress Message"
    )

    # Verify: Repository was NOT called
    mock_repo.update_fields.assert_not_called()

    # Verify: Local object remains unchanged
    assert job.steps[0].status == "completed"
    assert job.steps[0].message == "Final Message"


@pytest.mark.asyncio
async def test_update_step_progress_does_not_overwrite_top_level_fields(
    pipeline_service, mock_repo, mock_db
):
    # Setup: Job has some document counts
    job = PipelineJob(
        id="job-123",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="crawling",
        documents_found=10,
        documents_stored=5,
    )

    # Action: Update progress
    await pipeline_service._update_step_progress(mock_db, job, "crawling", current=2, total=10)

    # Verify: Repository call only contains step-specific fields
    mock_repo.update_fields.assert_called_once()
    args = mock_repo.update_fields.call_args[0][2]

    # Check that top-level fields are ABSENT from the update payload
    assert "status" not in args
    assert "documents_found" not in args
    assert "documents_stored" not in args

    # Check that step progress is present
    assert args["steps.0.progress_current"] == 2
    assert args["steps.0.progress_total"] == 10


@pytest.mark.asyncio
async def test_run_pipeline_zero_documents_marks_no_documents_not_failed(mock_db):
    """A crawl that completes but stores 0 documents is a valid terminal outcome.

    It must be marked ``no_documents`` (not ``failed``) so the product page does
    not retrigger the pipeline on every visit. ``failed`` is reserved for genuine
    interruptions/errors that warrant a retry.
    """
    job = PipelineJob(
        id="job-zero",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="pending",
    )

    repo = MagicMock(spec=PipelineRepository)
    repo.find_by_id = AsyncMock(return_value=job)
    repo.update = AsyncMock()
    repo.update_fields = AsyncMock()

    service = PipelineService(pipeline_repo=repo)

    product = SimpleNamespace(
        id="test-product-id", slug="test-product", name="Test Product", name_source=None
    )
    product_svc = MagicMock()
    product_svc.get_product_by_slug = AsyncMock(return_value=product)

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    @asynccontextmanager
    async def fake_db_session():
        yield mock_db

    # No pre-existing docs — confirms no_documents is still reached
    empty_doc_svc = MagicMock()
    empty_doc_svc.get_product_documents_by_slug = AsyncMock(return_value=[])

    with (
        patch("src.services.pipeline_service.db_session", fake_db_session),
        patch(
            "src.services.pipeline_service.create_product_service",
            return_value=product_svc,
        ),
        patch(
            "src.services.pipeline_service.create_document_service",
            return_value=empty_doc_svc,
        ),
        patch(
            "src.services.pipeline_service.PolicyDocumentPipeline",
            return_value=fake_pipeline,
        ),
    ):
        await service.run_pipeline("job-zero")

    assert job.status == "no_documents"
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_run_pipeline_all_documents_fail_analysis_is_truthful(mock_db):
    """Crawl succeeds but every document fails analysis.

    The job must fail at the ANALYSIS stage with a truthful, retry-oriented error
    (not a generic/crawl-flavored failure), the synthesising step must be marked
    failed (not "completed"), and overview synthesis must never run.
    """
    job = PipelineJob(
        id="job-analysis",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="pending",
    )

    repo = MagicMock(spec=PipelineRepository)
    repo.find_by_id = AsyncMock(return_value=job)
    repo.update = AsyncMock()
    repo.update_fields = AsyncMock()
    service = PipelineService(pipeline_repo=repo)

    product = SimpleNamespace(
        id="test-product-id", slug="test-product", name="Test Product", name_source=None
    )
    product_svc = MagicMock()
    product_svc.get_product_by_slug = AsyncMock(return_value=product)

    # Crawl found 3 documents — the crawl did NOT fail.
    crawl_stats = SimpleNamespace(
        total_documents_found=3,
        policy_documents_stored=3,
        crawl_errors=[],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    # Analysis returns the documents, but none got an `.analysis` (all failed).
    unanalysed_docs = [SimpleNamespace(analysis=None, doc_type="privacy_policy") for _ in range(3)]
    analyse_mock = AsyncMock(
        return_value=AnalysisResult(documents=unanalysed_docs, analyses_skipped=0)  # ty: ignore[invalid-argument-type]
    )
    overview_mock = AsyncMock()

    @asynccontextmanager
    async def fake_db_session():
        yield mock_db

    with (
        patch("src.services.pipeline_service.db_session", fake_db_session),
        patch(
            "src.services.pipeline_service.create_product_service",
            return_value=product_svc,
        ),
        patch("src.services.pipeline_service.create_document_service", return_value=MagicMock()),
        patch(
            "src.services.pipeline_service.PolicyDocumentPipeline",
            return_value=fake_pipeline,
        ),
        patch("src.services.pipeline_service.analyse_product_documents", analyse_mock),
        patch("src.services.pipeline_service.generate_product_overview", overview_mock),
    ):
        await service.run_pipeline("job-analysis")

    assert job.status == "analysis_failed"
    assert job.error == PipelineErrorCode.all_analysis_failed
    assert "could not analyze" in (job.error_detail or "").lower()
    # Crawl succeeded, so the truthful frontend can tell this is an analysis failure.
    assert job.documents_stored == 3
    # Overview synthesis must be skipped entirely.
    overview_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_step_progress_is_monotonic(pipeline_service, mock_repo, mock_db):
    # The crawl frontier grows as new links are discovered, so a raw
    # current/total ratio can drop. The reported percent must never regress.
    job = PipelineJob(
        id="job-123",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="crawling",
        steps=[PipelineStep(name="crawling", status="running")],
    )

    # First update: 5 of 10 -> 50%
    await pipeline_service._update_step_progress(mock_db, job, "crawling", current=5, total=10)
    assert job.steps[0].progress_percent == 50.0

    # Frontier grew: 6 of 40 would be 15%, but the bar must not move backwards.
    await pipeline_service._update_step_progress(mock_db, job, "crawling", current=6, total=40)
    assert job.steps[0].progress_percent == 50.0
    # The regressed percent must not be written to the DB payload either.
    last_args = mock_repo.update_fields.call_args[0][2]
    assert "steps.0.progress_percent" not in last_args
    # Live counts still update so the message/count stay truthful.
    assert last_args["steps.0.progress_current"] == 6
    assert last_args["steps.0.progress_total"] == 40

    # Genuine forward progress advances the bar.
    await pipeline_service._update_step_progress(mock_db, job, "crawling", current=30, total=40)
    assert job.steps[0].progress_percent == 75.0


def _pipeline_run_patches(mock_db, fake_pipeline, product_svc):
    """The patch set that lets run_pipeline reach the stall-guard wiring deterministically."""

    @asynccontextmanager
    async def fake_db_session():
        yield mock_db

    return (
        patch("src.services.pipeline_service.db_session", fake_db_session),
        patch("src.services.pipeline_service.create_product_service", return_value=product_svc),
        patch("src.services.pipeline_service.PolicyDocumentPipeline", return_value=fake_pipeline),
    )


@pytest.mark.asyncio
async def test_run_pipeline_no_wall_clock_cap_by_default(mock_db, monkeypatch):
    """With the cap disabled (default), the core is never wrapped in a wall-clock wait_for.

    A legitimately long crawl (e.g. a multi-jurisdiction site running for hours) must not be
    guillotined; liveness is the stall guard + max_pages, not total runtime.
    """
    monkeypatch.setattr(ps, "MAX_PIPELINE_DURATION_SECONDS", 0.0)

    job = PipelineJob(
        id="job-long",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="pending",
    )
    repo = MagicMock(spec=PipelineRepository)
    repo.find_by_id = AsyncMock(return_value=job)
    repo.update = AsyncMock()
    repo.update_fields = AsyncMock()
    service = PipelineService(pipeline_repo=repo)

    product = SimpleNamespace(
        id="test-product-id", slug="test-product", name="Test Product", name_source=None
    )
    product_svc = MagicMock()
    product_svc.get_product_by_slug = AsyncMock(return_value=product)

    crawl_stats = SimpleNamespace(
        total_documents_found=0,
        policy_documents_stored=0,
        crawl_errors=[],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    wait_for_calls: list[float | None] = []
    real_wait_for = asyncio.wait_for

    async def recording_wait_for(awaitable, timeout):
        wait_for_calls.append(timeout)
        return await real_wait_for(awaitable, timeout)

    patches = _pipeline_run_patches(mock_db, fake_pipeline, product_svc)
    with patches[0], patches[1], patches[2]:
        monkeypatch.setattr(ps.asyncio, "wait_for", recording_wait_for)
        await service.run_pipeline("job-long")

    # The stall guard was awaited directly — no finite wall-clock timeout wrapped the core.
    assert not wait_for_calls
    assert job.error != PipelineErrorCode.timed_out


@pytest.mark.asyncio
async def test_run_pipeline_opt_in_cap_marks_timed_out(mock_db, monkeypatch):
    """When PIPELINE_MAX_DURATION_SECONDS is set > 0, the wall-clock backstop still fires."""
    monkeypatch.setattr(ps, "MAX_PIPELINE_DURATION_SECONDS", 0.05)

    job = PipelineJob(
        id="job-capped",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="pending",
    )
    repo = MagicMock(spec=PipelineRepository)
    repo.find_by_id = AsyncMock(return_value=job)
    repo.update = AsyncMock()
    repo.update_fields = AsyncMock()
    service = PipelineService(pipeline_repo=repo)

    product = SimpleNamespace(
        id="test-product-id", slug="test-product", name="Test Product", name_source=None
    )
    product_svc = MagicMock()
    product_svc.get_product_by_slug = AsyncMock(return_value=product)

    # A crawl that outlives the opt-in cap (but is making progress, so the stall guard wouldn't
    # touch it) must still be aborted by the wall-clock backstop.
    async def slow_run(*args, **kwargs):
        await asyncio.sleep(5)
        return SimpleNamespace(
            total_documents_found=0,
            policy_documents_stored=0,
            crawl_errors=[],
            crawl_skip_reasons=[],
        )

    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(side_effect=slow_run)

    patches = _pipeline_run_patches(mock_db, fake_pipeline, product_svc)
    with patches[0], patches[1], patches[2]:
        await service.run_pipeline("job-capped")

    assert job.error == PipelineErrorCode.timed_out
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_overview_stage_heartbeats_during_synthesis(mock_db):
    """The overview stage bumps the job heartbeat at each synthesis sub-step.

    Overview synthesis (aggregation rebuild + LLM calls + explainer + compliance) does no DB
    write of its own and can outlast the stall window on a large core-doc set. The stage must
    thread a heartbeat callback into generate_product_overview so updated_at/last_heartbeat are
    refreshed before a healthy-but-slow synthesis trips the no-progress stall guard.
    """
    job = PipelineJob(
        id="job-overview",
        product_slug="test-product",
        product_name="Test Product",
        url="https://test.com",
        status="pending",
    )

    repo = MagicMock(spec=PipelineRepository)
    repo.find_by_id = AsyncMock(return_value=job)
    repo.update = AsyncMock()
    repo.update_fields = AsyncMock()
    service = PipelineService(pipeline_repo=repo)

    product = SimpleNamespace(
        id="test-product-id", slug="test-product", name="Test Product", name_source=None
    )
    product_svc = MagicMock()
    product_svc.get_product_by_slug = AsyncMock(return_value=product)
    product_svc.get_product_overview_data = AsyncMock(return_value={"overview": {"summary": "ok"}})
    product_svc.save_product_explainer = AsyncMock(return_value=True)
    product_svc.save_product_compliance = AsyncMock(return_value=True)

    crawl_stats = SimpleNamespace(
        total_documents_found=1,
        policy_documents_stored=1,
        crawl_errors=[],
        crawl_skip_reasons=[],
    )
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=crawl_stats)

    analysed_docs = [SimpleNamespace(analysis=object(), doc_type="privacy_policy")]
    analyse_mock = AsyncMock(
        return_value=AnalysisResult(documents=analysed_docs, analyses_skipped=0)  # ty: ignore[invalid-argument-type]
    )

    # Stand in for the real generator: fire the threaded heartbeat callback the same number of
    # times the real one does (once per long sub-step) so the assertion exercises the wiring.
    async def fake_generate_overview(*_args, on_progress=None, **_kwargs):
        assert on_progress is not None, "overview stage must thread a heartbeat callback"
        await on_progress()
        await on_progress()

    overview_mock = AsyncMock(side_effect=fake_generate_overview)

    @asynccontextmanager
    async def fake_db_session():
        yield mock_db

    with (
        patch("src.services.pipeline_service.db_session", fake_db_session),
        patch("src.services.pipeline_service.create_product_service", return_value=product_svc),
        patch("src.services.pipeline_service.create_document_service", return_value=MagicMock()),
        patch("src.services.pipeline_service.PolicyDocumentPipeline", return_value=fake_pipeline),
        patch("src.services.pipeline_service.analyse_product_documents", analyse_mock),
        patch("src.services.pipeline_service.generate_product_overview", overview_mock),
        patch(
            "src.services.pipeline_service.generate_product_consumer_explainer",
            AsyncMock(return_value=None),
        ),
        patch(
            "src.services.pipeline_service.generate_product_compliance",
            AsyncMock(return_value=None),
        ),
    ):
        await service.run_pipeline("job-overview")

    assert job.status == "completed"

    # The generating_overview step is index 2 in the default step list. Find every progress
    # write the stage emitted for it and confirm each carried the liveness heartbeat — both the
    # in-synthesis pings and the pre-explainer / pre-compliance pings.
    overview_heartbeats = [
        call.args[2]
        for call in repo.update_fields.await_args_list
        if "steps.2.message" in call.args[2] and "last_heartbeat" in call.args[2]
    ]
    # 2 in-synthesis pings + 1 before explainer + 1 before compliance.
    assert len(overview_heartbeats) >= 4
    assert all(fields["last_heartbeat"] is not None for fields in overview_heartbeats)
