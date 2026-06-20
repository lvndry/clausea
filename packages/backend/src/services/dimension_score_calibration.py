"""Pass-through for privacy dimension scores from structured LLM output.

Dimension scores (0-10, higher is better for the user) are trusted as emitted by
the LLM against the analysis rubric in prompts. This module preserves the
calibration API for callers but does not rewrite scores via regex on
justifications.
"""

from __future__ import annotations

from typing import Literal

from src.models.document import (
    DocumentAnalysisScores,
    MetaSummary,
    MetaSummaryScores,
)

DimensionKey = Literal[
    "transparency",
    "data_collection_scope",
    "user_control",
    "third_party_sharing",
    "data_retention_score",
    "security_score",
]

_OVERVIEW_DIMENSIONS: tuple[str, ...] = (
    "transparency",
    "data_collection_scope",
    "user_control",
    "third_party_sharing",
)


def calibrate_dimension_score(
    dimension: str,
    score: int,
    justification: str,
) -> int:
    """Return the LLM dimension score unchanged."""
    _ = dimension, justification
    return score


def calibrate_document_scores(
    scores: dict[str, DocumentAnalysisScores],
) -> dict[str, DocumentAnalysisScores]:
    """Return document analysis dimension scores unchanged."""
    return scores


def calibrate_meta_summary_scores(scores: MetaSummaryScores) -> MetaSummaryScores:
    """Return overview dimension scores unchanged."""
    return scores


def calibrate_meta_summary(meta_summary: MetaSummary) -> None:
    """No-op: overview dimension scores are already calibrated by the LLM rubric."""
    meta_summary.scores = calibrate_meta_summary_scores(meta_summary.scores)
