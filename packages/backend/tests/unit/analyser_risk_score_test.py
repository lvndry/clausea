"""Tests for grade-based privacy risk derivation."""

from src.analyser import (
    _calculate_overview_risk_score,
    _calculate_risk_score,
    _ensure_required_scores,
    _is_protective_finding_value,
    _reconcile_meta_summary_risk,
    _weighted_product_risk_score,
)
from src.models.document import (
    Document,
    DocumentAnalysis,
    DocumentAnalysisScores,
    MetaSummary,
    MetaSummaryScore,
    MetaSummaryScores,
    PrivacySignals,
    TopicStanceBreakdown,
)


def _grade(letter: str, justification: str = "ok") -> DocumentAnalysisScores:
    return DocumentAnalysisScores(grade=letter, justification=justification)  # type: ignore[arg-type]


def _doc(
    *,
    doc_type: str,
    risk: int,
    url: str = "https://example.com/p",
    product_id: str = "p1",
) -> Document:
    analysis = DocumentAnalysis(
        summary="x",
        scores={
            "transparency": _grade("C"),
            "data_collection_scope": _grade("C"),
            "user_control": _grade("C"),
            "third_party_sharing": _grade("C"),
            "data_retention_score": _grade("C"),
            "security_score": _grade("C"),
        },
        grade="C",
        risk_score=risk,
        verdict="moderate",
        keypoints=[],
        critical_clauses=[],
        document_risk_breakdown=None,
        key_sections=[],
    )
    return Document(
        url=url,
        product_id=product_id,
        doc_type=doc_type,  # type: ignore[arg-type]
        markdown="",
        text="",
        analysis=analysis,
    )


def test_calculate_risk_score_privacy_friendly_grades() -> None:
    scores = {
        key: _grade("A")
        for key in (
            "transparency",
            "data_collection_scope",
            "user_control",
            "third_party_sharing",
            "data_retention_score",
            "security_score",
        )
    }
    assert _calculate_risk_score(scores) == 1


def test_calculate_risk_score_invasive_grades() -> None:
    scores = {
        "transparency": _grade("B"),
        "data_collection_scope": _grade("E"),
        "user_control": _grade("D"),
        "third_party_sharing": _grade("E"),
        "data_retention_score": _grade("D"),
        "security_score": _grade("D"),
    }
    assert _calculate_risk_score(scores) == 7


def test_weighted_product_risk_privacy_policy_dominates() -> None:
    docs = [
        _doc(doc_type="privacy_policy", risk=2),
        _doc(doc_type="terms_of_service", risk=8),
    ]
    assert _weighted_product_risk_score(docs) == 4


def test_no_weighted_dimensions_returns_none() -> None:
    assert _calculate_risk_score({}) is None


def test_ensure_required_scores_preserves_llm_grade() -> None:
    parsed = DocumentAnalysis(
        summary="ok",
        grade="B",
        grade_justification="Solid controls with minor gaps.",
        scores={
            "transparency": _grade("B", "Clear disclosures"),
            "data_collection_scope": _grade("C", "Broad collection"),
        },
    )
    result = _ensure_required_scores(parsed)
    assert result.grade == "B"
    assert result.grade_justification == "Solid controls with minor gaps."
    assert result.risk_score == 3


def test_reconcile_meta_summary_uses_llm_grade() -> None:
    meta = MetaSummary(
        summary="ok",
        grade="B",
        grade_justification="Mostly fair with some sharing concerns.",
        scores=MetaSummaryScores(
            transparency=MetaSummaryScore(grade="B", justification="Clear"),
            data_collection_scope=MetaSummaryScore(grade="C", justification="Broad"),
            user_control=MetaSummaryScore(grade="B", justification="Some controls"),
            third_party_sharing=MetaSummaryScore(grade="D", justification="Wide sharing"),
        ),
    )
    _reconcile_meta_summary_risk(meta)
    assert meta.grade == "B"
    assert meta.risk_score is not None


def test_overview_risk_from_dimension_grades() -> None:
    scores = MetaSummaryScores(
        transparency=MetaSummaryScore(grade="B", justification="Clear but not exhaustive"),
        data_collection_scope=MetaSummaryScore(grade="C", justification="Broad collection"),
        user_control=MetaSummaryScore(
            grade="B",
            justification="Cookie banner, GPC, AI toggle, self-service deletion.",
        ),
        third_party_sharing=MetaSummaryScore(grade="D", justification="Wide sharing"),
    )
    risk = _calculate_overview_risk_score(scores)
    assert risk in {5, 7}


def test_protective_finding_rejects_no_substring_false_positives() -> None:
    assert not _is_protective_finding_value("data_sale", "We provide notice of data practices")
    assert not _is_protective_finding_value(
        "data_sale", "Information is not shared with third parties"
    )
    assert _is_protective_finding_value("data_sale", "sells_data: no")
    assert _is_protective_finding_value("data_sale", "does not sell personal data")
    assert not _is_protective_finding_value("ai_training", "We provide notification of updates")
    assert _is_protective_finding_value("ai_training", "no ai training on user content")


def test_signal_floor_holds_after_positive_adjustment() -> None:
    meta = MetaSummary(
        summary="ok",
        grade="B",
        scores=MetaSummaryScores(
            transparency=MetaSummaryScore(grade="B", justification="Clear"),
            data_collection_scope=MetaSummaryScore(grade="B", justification="Limited"),
            user_control=MetaSummaryScore(grade="B", justification="Controls"),
            third_party_sharing=MetaSummaryScore(grade="B", justification="Limited sharing"),
        ),
        privacy_signals=PrivacySignals(sells_data="yes"),
        benefits=["encryption at rest", "self-service deletion"],
        topic_stances=[
            TopicStanceBreakdown(topic="data_sale", status="found", stance="low_risk"),
            TopicStanceBreakdown(topic="ai_training", status="found", stance="low_risk"),
            TopicStanceBreakdown(topic="security", status="found", stance="low_risk"),
        ],
    )
    _reconcile_meta_summary_risk(meta)
    assert meta.risk_score == 6
