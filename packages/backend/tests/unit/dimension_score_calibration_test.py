"""Tests for fair dimension score calibration."""

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


def test_figma_user_control_score_five_raises_to_b_or_better() -> None:
    """Multiple real opt-outs with minor caveats must not stay at C-range."""
    adjusted = calibrate_dimension_score(
        "user_control",
        5,
        FIGMA_USER_CONTROL_JUSTIFICATION,
    )
    assert adjusted >= 7, "Strong controls with caveats should reach B+ (score >= 7)"


def test_figma_user_control_via_meta_summary_calibration() -> None:
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
    assert calibrated.user_control.score >= 7


def test_user_control_does_not_raise_when_no_controls_documented() -> None:
    adjusted = calibrate_dimension_score(
        "user_control",
        3,
        "No self-service deletion; users must email support to request removal.",
    )
    assert adjusted == 3


def test_user_control_does_not_raise_when_explicitly_none() -> None:
    adjusted = calibrate_dimension_score(
        "user_control",
        2,
        "No opt-out provided. Cannot delete account. Contact us to request removal.",
    )
    assert adjusted == 2


def test_transparency_positive_justification_gets_floor() -> None:
    adjusted = calibrate_dimension_score(
        "transparency",
        4,
        "Clearly explains what is collected and specifically names third-party recipients.",
    )
    assert adjusted >= 6


def test_document_scores_calibration_recalculates_risk_inputs() -> None:
    scores = {
        "user_control": DocumentAnalysisScores(
            score=5,
            justification=FIGMA_USER_CONTROL_JUSTIFICATION,
        ),
    }
    calibrated = calibrate_document_scores(scores)
    assert calibrated["user_control"].score >= 7


def test_calibrate_meta_summary_in_place() -> None:
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
    assert meta.scores.user_control.score >= 7


def test_sharing_negative_justification_not_inflated() -> None:
    adjusted = calibrate_dimension_score(
        "third_party_sharing",
        2,
        "Sells personal data to data brokers and many advertising partners.",
    )
    assert adjusted == 2
