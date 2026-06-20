"""Tests for dimension score pass-through (LLM scores trusted as-is)."""

from src.models.document import (
    DocumentAnalysisScores,
    MetaSummary,
    MetaSummaryScore,
    MetaSummaryScores,
)
from src.services.dimension_score_calibration import (
    calibrate_dimension_score,
    calibrate_document_scores,
    calibrate_meta_summary,
    calibrate_meta_summary_scores,
)

FIGMA_USER_CONTROL_JUSTIFICATION = (
    "Provides cookie consent banner, recognizes Global Privacy Control (GPC), "
    "an AI Content Training toggle, marketing unsubscribe, and self-service account "
    "deletion. Caveats: account deletion is all-or-nothing, mobile cookie opt-outs "
    "are limited, and org-level AI toggle applies for enterprise admins."
)


def test_calibrate_dimension_score_is_pass_through() -> None:
    adjusted = calibrate_dimension_score(
        "user_control",
        5,
        FIGMA_USER_CONTROL_JUSTIFICATION,
    )
    assert adjusted == 5


def test_calibrate_meta_summary_scores_is_pass_through() -> None:
    scores = MetaSummaryScores(
        transparency=MetaSummaryScore(score=6, justification="Clear but not exhaustive"),
        data_collection_scope=MetaSummaryScore(score=4, justification="Broad collection"),
        user_control=MetaSummaryScore(
            score=5,
            justification=FIGMA_USER_CONTROL_JUSTIFICATION,
        ),
        third_party_sharing=MetaSummaryScore(score=3, justification="Wide sharing"),
    )
    calibrated = calibrate_meta_summary_scores(scores)
    assert calibrated.user_control.score == 5


def test_calibrate_document_scores_is_pass_through() -> None:
    scores = {
        "user_control": DocumentAnalysisScores(
            score=5,
            justification=FIGMA_USER_CONTROL_JUSTIFICATION,
        ),
    }
    calibrated = calibrate_document_scores(scores)
    assert calibrated["user_control"].score == 5


def test_calibrate_meta_summary_in_place_is_no_op() -> None:
    meta = MetaSummary(
        summary="ok",
        scores=MetaSummaryScores(
            transparency=MetaSummaryScore(score=6, justification="ok"),
            data_collection_scope=MetaSummaryScore(score=4, justification="ok"),
            user_control=MetaSummaryScore(
                score=5,
                justification=FIGMA_USER_CONTROL_JUSTIFICATION,
            ),
            third_party_sharing=MetaSummaryScore(score=3, justification="ok"),
        ),
        risk_score=9,
        verdict="very_pervasive",
    )
    calibrate_meta_summary(meta)
    assert meta.scores.user_control.score == 5
