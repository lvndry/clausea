"""Tests for deterministic privacy risk scoring and product-level blending."""

from src.analyser import _calculate_risk_score, _weighted_product_risk_score
from src.models.document import Document, DocumentAnalysis, DocumentAnalysisScores


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
            "transparency": DocumentAnalysisScores(score=5, justification=""),
            "data_collection_scope": DocumentAnalysisScores(score=5, justification=""),
            "user_control": DocumentAnalysisScores(score=5, justification=""),
            "third_party_sharing": DocumentAnalysisScores(score=5, justification=""),
            "data_retention_score": DocumentAnalysisScores(score=5, justification=""),
            "security_score": DocumentAnalysisScores(score=5, justification=""),
        },
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


def test_calculate_risk_score_privacy_friendly_high_components() -> None:
    scores = {
        k: DocumentAnalysisScores(score=9, justification="")
        for k in (
            "transparency",
            "data_collection_scope",
            "user_control",
            "third_party_sharing",
            "data_retention_score",
            "security_score",
        )
    }
    assert _calculate_risk_score(scores) == 1


def test_calculate_risk_score_invasive_low_components() -> None:
    scores = {
        "transparency": DocumentAnalysisScores(score=6, justification=""),
        "data_collection_scope": DocumentAnalysisScores(score=2, justification=""),
        "user_control": DocumentAnalysisScores(score=3, justification=""),
        "third_party_sharing": DocumentAnalysisScores(score=2, justification=""),
        "data_retention_score": DocumentAnalysisScores(score=3, justification=""),
        "security_score": DocumentAnalysisScores(score=4, justification=""),
    }
    assert _calculate_risk_score(scores) == 7


def test_weighted_product_risk_privacy_policy_dominates() -> None:
    docs = [
        _doc(doc_type="privacy_policy", risk=2),
        _doc(doc_type="terms_of_service", risk=8),
    ]
    assert _weighted_product_risk_score(docs) == 4


def test_weighted_product_risk_skips_missing_analysis() -> None:
    d = Document(
        url="https://example.com",
        product_id="p",
        doc_type="privacy_policy",
        markdown="",
        text="",
        analysis=None,
    )
    assert _weighted_product_risk_score([d]) is None


def test_other_docs_excluded_from_weighted_score() -> None:
    """'other' documents must never influence the product risk score."""
    privacy = _doc(doc_type="privacy_policy", risk=8)
    other = _doc(doc_type="other", risk=0)  # artificially low — should be ignored
    score = _weighted_product_risk_score([privacy, other])
    assert score == 8  # only privacy_policy contributes
