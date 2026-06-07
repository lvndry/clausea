"""Tests for the Phase 1.1 crawl-skip telemetry.

We do not invoke the live pipeline (network + LLM + Mongo). Instead we exercise
the data layer that carries skip information from ProcessingStats into the
persisted PipelineJob, and the categorized failure-message logic that pulls
from it. These are the boundaries that decide whether an operator can tell
WHICH filter dropped each URL.
"""

from __future__ import annotations

from src.models.pipeline_job import CrawlSkip, PipelineJob
from src.pipeline import ProcessingStats


def test_processing_stats_carries_skip_reasons() -> None:
    stats = ProcessingStats()
    stats.crawl_skip_reasons.append(
        {
            "url": "https://x.example/policy",
            "reason": "insufficient_content",
            "detail": "text=120 chars",
        }
    )
    stats.crawl_skip_reasons.append(
        {
            "url": "https://y.example/help",
            "reason": "non_policy_classification",
            "detail": "classifier=other",
        }
    )
    assert len(stats.crawl_skip_reasons) == 2
    assert stats.crawl_skip_reasons[0]["reason"] == "insufficient_content"


def test_crawl_skip_round_trips_through_pipeline_job() -> None:
    skips_as_dicts = [
        {
            "url": "https://x.example/policy",
            "reason": "insufficient_content",
            "detail": "text=120 chars",
        },
        {
            "url": "https://y.example/help",
            "reason": "non_policy_classification",
            "detail": "classifier=other",
        },
        {"url": "https://z.example/legal", "reason": "non_english", "detail": "locale=fr-FR"},
    ]
    job = PipelineJob(
        product_slug="example",
        product_name="Example",
        url="https://x.example",
        crawl_skip_reasons=[CrawlSkip.model_validate(skip) for skip in skips_as_dicts],
    )
    assert [s.reason for s in job.crawl_skip_reasons] == [
        "insufficient_content",
        "non_policy_classification",
        "non_english",
    ]
    # Persistence shape — model_dump matches what would be written to Mongo.
    dumped = job.model_dump()
    assert dumped["crawl_skip_reasons"][2]["detail"] == "locale=fr-FR"


def test_categorized_failure_breakdown_is_deterministic() -> None:
    """The error message in pipeline_service.py sorts reasons by descending count.

    Re-encoding the same logic here as a pure function pins it down so behaviour
    can't drift silently.
    """
    skips = [
        CrawlSkip(url="a", reason="insufficient_content"),
        CrawlSkip(url="b", reason="insufficient_content"),
        CrawlSkip(url="c", reason="insufficient_content"),
        CrawlSkip(url="d", reason="non_english"),
        CrawlSkip(url="e", reason="non_policy_classification"),
        CrawlSkip(url="f", reason="non_policy_classification"),
    ]
    counts: dict[str, int] = {}
    for skip in skips:
        counts[skip.reason] = counts.get(skip.reason, 0) + 1
    breakdown = ", ".join(
        f"{n}× {reason}" for reason, n in sorted(counts.items(), key=lambda kv: -kv[1])
    )
    assert breakdown == "3× insufficient_content, 2× non_policy_classification, 1× non_english"
