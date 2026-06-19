"""Unit tests for the domain-level circuit breaker on the pipeline job queue.

Covers:
- Hard vs transient crawl-error classification (is_hard_crawl_error)
- claim_next_pending_job: domain under threshold is claimable
- claim_next_pending_job: domain at/above threshold is blocked (job → failed)
- requeue_failed_jobs: accumulates hard failure counts from crawl_errors without reset
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.pipeline_job import PipelineErrorCode, is_hard_crawl_error
from src.repositories import pipeline_repository as pr
from src.repositories.pipeline_repository import PipelineRepository

# ---------------------------------------------------------------------------
# Hard vs transient failure classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_type, status_code, error_message, expected",
    [
        # Hard: HTTP 403 Forbidden
        ("http_error", 403, "403 Forbidden", True),
        # Hard: HTTP 401 Unauthorized
        ("http_error", 401, None, True),
        # Hard: HTTP 451 Unavailable For Legal Reasons
        ("http_error", 451, "Unavailable For Legal Reasons", True),
        # Hard: error message contains CAPTCHA keyword (any status)
        ("http_error", 200, "Please solve a captcha to continue", True),
        # Hard: error message contains Cloudflare reference
        ("unknown", 0, "Blocked by Cloudflare DDoS protection", True),
        # Hard: "Access Denied" in message
        ("http_error", 403, "Access Denied — automated access not allowed", True),
        # Transient: network timeout
        ("timeout", 0, "Request timed out after 30s", False),
        # Transient: network/DNS error
        ("network_error", 0, "Connection refused", False),
        # Transient: 5xx server error
        ("http_error", 503, "Service Unavailable", False),
        # Transient: 429 rate-limiting (not a hard block)
        ("http_error", 429, "Too Many Requests", False),
        # Transient: robots.txt block (policy, not bot detection)
        ("robots_txt_blocked", 0, "Blocked by robots.txt", False),
        # Transient: 404 Not Found
        ("http_error", 404, "Not Found", False),
        # Unknown / empty message — conservative: not hard
        ("unknown", 0, None, False),
    ],
)
def test_is_hard_crawl_error_classification(
    error_type: str, status_code: int, error_message: str | None, expected: bool
) -> None:
    result = is_hard_crawl_error(error_type, status_code, error_message)
    assert result is expected, (
        f"is_hard_crawl_error({error_type!r}, {status_code}, {error_message!r}) "
        f"returned {result}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# claim_next_pending_job — helper mock builders
# ---------------------------------------------------------------------------


def _make_db_for_claim(
    *,
    pending_doc: dict | None,
    find_and_update_result: dict | None = None,
) -> MagicMock:
    """Build a mock db where find_one returns pending_doc and find_one_and_update returns result."""
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=pending_doc)
    collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    collection.find_one_and_update = AsyncMock(return_value=find_and_update_result)

    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=collection)
    return db


# ---------------------------------------------------------------------------
# claim: under threshold → job is claimed normally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_proceeds_when_under_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr, "DOMAIN_CIRCUIT_BREAKER_THRESHOLD", 5)

    pending = {
        "id": "job-1",
        "product_slug": "example",
        "product_name": "Example",
        "url": "https://example.com",
        "accumulated_hard_failure_count": 4,  # one below threshold
        "status": "pending",
        "created_at": "2024-01-01T00:00:00",
    }
    claimed = {**pending, "status": "crawling", "attempts": 1}

    db = _make_db_for_claim(pending_doc=pending, find_and_update_result=claimed)
    collection = db[PipelineRepository.COLLECTION]

    job = await PipelineRepository().claim_next_pending_job(db)

    # Job was claimed (find_one_and_update was called)
    collection.find_one_and_update.assert_awaited_once()
    # No circuit-break update was issued
    circuit_break_calls = [
        call
        for call in collection.update_one.await_args_list
        if call.args
        and isinstance(call.args[1], dict)
        and call.args[1].get("$set", {}).get("error") == PipelineErrorCode.domain_circuit_breaker
    ]
    assert not circuit_break_calls
    assert job is not None
    assert job.status == "crawling"


@pytest.mark.asyncio
async def test_claim_proceeds_when_no_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh job (accumulated_hard_failure_count missing / zero) is always claimable."""
    monkeypatch.setattr(pr, "DOMAIN_CIRCUIT_BREAKER_THRESHOLD", 5)

    pending = {
        "id": "job-2",
        "product_slug": "newsite",
        "product_name": "New Site",
        "url": "https://newsite.io",
        # accumulated_hard_failure_count absent — treated as 0
        "status": "pending",
        "created_at": "2024-01-01T00:00:00",
    }
    claimed = {**pending, "status": "crawling", "attempts": 1, "accumulated_hard_failure_count": 0}

    db = _make_db_for_claim(pending_doc=pending, find_and_update_result=claimed)
    collection = db[PipelineRepository.COLLECTION]

    job = await PipelineRepository().claim_next_pending_job(db)

    collection.find_one_and_update.assert_awaited_once()
    assert job is not None


# ---------------------------------------------------------------------------
# claim: at/above threshold → job is circuit-broken, None returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_circuit_breaks_at_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr, "DOMAIN_CIRCUIT_BREAKER_THRESHOLD", 5)

    pending = {
        "id": "job-cb",
        "product_slug": "blocked-site",
        "url": "https://blocked-site.com",
        "accumulated_hard_failure_count": 5,  # exactly at threshold
        "status": "pending",
        "created_at": "2024-01-01T00:00:00",
    }

    db = _make_db_for_claim(pending_doc=pending)
    collection = db[PipelineRepository.COLLECTION]

    job = await PipelineRepository().claim_next_pending_job(db)

    # Must return None — nothing was claimed
    assert job is None

    # find_one_and_update (normal claim path) must NOT have been called
    collection.find_one_and_update.assert_not_awaited()

    # update_one must have been called to mark the job as circuit-broken
    collection.update_one.assert_awaited_once()
    _filter, update = collection.update_one.call_args.args
    assert _filter == {"id": "job-cb", "status": "pending"}
    fields = update["$set"]
    assert fields["status"] == "failed"
    assert fields["active"] is False
    assert fields["error"] == PipelineErrorCode.domain_circuit_breaker.value
    assert fields["auto_retry_disabled"] is True


@pytest.mark.asyncio
async def test_claim_circuit_breaks_above_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr, "DOMAIN_CIRCUIT_BREAKER_THRESHOLD", 3)

    pending = {
        "id": "job-above",
        "product_slug": "anti-bot-site",
        "url": "https://anti-bot.example.org",
        "accumulated_hard_failure_count": 10,  # well above threshold
        "status": "pending",
        "created_at": "2024-01-01T00:00:00",
    }

    db = _make_db_for_claim(pending_doc=pending)
    collection = db[PipelineRepository.COLLECTION]

    job = await PipelineRepository().claim_next_pending_job(db)

    assert job is None
    collection.find_one_and_update.assert_not_awaited()
    collection.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_returns_none_when_no_pending_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr, "DOMAIN_CIRCUIT_BREAKER_THRESHOLD", 5)

    db = _make_db_for_claim(pending_doc=None)
    collection = db[PipelineRepository.COLLECTION]

    job = await PipelineRepository().claim_next_pending_job(db)

    assert job is None
    # Neither claim nor circuit-break update should run
    collection.find_one_and_update.assert_not_awaited()
    collection.update_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# requeue_failed_jobs: hard failure accumulation
# ---------------------------------------------------------------------------


def _failed_jobs_collection_with_errors(
    candidates: list[dict],
) -> MagicMock:
    """Mock collection for requeue tests: no active slugs, supplied candidates."""
    collection = MagicMock()
    collection.distinct = AsyncMock(return_value=[])  # no currently-active jobs
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.to_list = AsyncMock(return_value=candidates)
    collection.find = MagicMock(return_value=cursor)
    collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    return collection


@pytest.mark.asyncio
async def test_requeue_accumulates_hard_failure_count() -> None:
    """Hard crawl errors are counted and added to accumulated_hard_failure_count on requeue."""
    hard_errors = [
        {
            "url": "https://example.com/page1",
            "status_code": 403,
            "error_type": "http_error",
            "error_message": "403 Forbidden",
        },
        {
            "url": "https://example.com/page2",
            "status_code": 403,
            "error_type": "http_error",
            "error_message": "Forbidden",
        },
        {
            "url": "https://example.com/page3",
            "status_code": 503,
            "error_type": "http_error",
            "error_message": "Service Unavailable",
        },  # transient
    ]
    candidate = {
        "id": "job-acc",
        "product_slug": "example",
        "attempts": 1,
        "error": PipelineErrorCode.crawl_failed.value,
        "crawl_errors": hard_errors,
        "accumulated_hard_failure_count": 1,  # one from previous attempt
    }

    collection = _failed_jobs_collection_with_errors([candidate])
    db = MagicMock()
    db.__getitem__.return_value = collection

    requeued = await PipelineRepository().requeue_failed_jobs(db)

    assert requeued == 1
    update_payload = collection.update_one.call_args.args[1]["$set"]
    # 2 hard errors this attempt + 1 existing = 3
    assert update_payload["accumulated_hard_failure_count"] == 3
    # crawl_errors still cleared
    assert update_payload["crawl_errors"] == []


@pytest.mark.asyncio
async def test_requeue_does_not_increment_for_transient_errors() -> None:
    """Transient crawl errors (timeout, network, 5xx) do not increment the hard counter."""
    transient_errors = [
        {
            "url": "https://example.com/page1",
            "status_code": 0,
            "error_type": "timeout",
            "error_message": "Request timed out",
        },
        {
            "url": "https://example.com/page2",
            "status_code": 503,
            "error_type": "http_error",
            "error_message": "Service Unavailable",
        },
        {
            "url": "https://example.com/page3",
            "status_code": 0,
            "error_type": "network_error",
            "error_message": "DNS resolution failed",
        },
    ]
    candidate = {
        "id": "job-transient",
        "product_slug": "example",
        "attempts": 2,
        "error": PipelineErrorCode.crawl_failed.value,
        "crawl_errors": transient_errors,
        "accumulated_hard_failure_count": 2,  # only 2 from previous hard failures
    }

    collection = _failed_jobs_collection_with_errors([candidate])
    db = MagicMock()
    db.__getitem__.return_value = collection

    requeued = await PipelineRepository().requeue_failed_jobs(db)

    assert requeued == 1
    update_payload = collection.update_one.call_args.args[1]["$set"]
    # No additional hard failures this attempt
    assert update_payload["accumulated_hard_failure_count"] == 2


@pytest.mark.asyncio
async def test_requeue_preserves_zero_count_when_no_crawl_errors() -> None:
    """A job with no crawl_errors (e.g. LLM analysis failure) keeps its existing counter."""
    candidate = {
        "id": "job-no-errors",
        "product_slug": "example",
        "attempts": 1,
        "error": PipelineErrorCode.all_analysis_failed.value,
        "crawl_errors": [],
        "accumulated_hard_failure_count": 0,
    }

    collection = _failed_jobs_collection_with_errors([candidate])
    db = MagicMock()
    db.__getitem__.return_value = collection

    await PipelineRepository().requeue_failed_jobs(db)

    update_payload = collection.update_one.call_args.args[1]["$set"]
    assert update_payload["accumulated_hard_failure_count"] == 0


@pytest.mark.asyncio
async def test_requeue_handles_missing_accumulated_field() -> None:
    """Old documents without accumulated_hard_failure_count are treated as starting at 0."""
    hard_errors = [
        {
            "url": "https://legacy.com/p",
            "status_code": 403,
            "error_type": "http_error",
            "error_message": "Access Denied",
        },
    ]
    candidate = {
        "id": "job-legacy",
        "product_slug": "legacy",
        "attempts": 1,
        "error": PipelineErrorCode.crawl_failed.value,
        "crawl_errors": hard_errors,
        # accumulated_hard_failure_count intentionally absent (legacy document)
    }

    collection = _failed_jobs_collection_with_errors([candidate])
    db = MagicMock()
    db.__getitem__.return_value = collection

    await PipelineRepository().requeue_failed_jobs(db)

    update_payload = collection.update_one.call_args.args[1]["$set"]
    assert update_payload["accumulated_hard_failure_count"] == 1
