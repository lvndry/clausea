from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.pipeline_job import PipelineJob, PipelineStep
from src.repositories.pipeline_repository import PipelineRepository
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
        status="summarizing",
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
