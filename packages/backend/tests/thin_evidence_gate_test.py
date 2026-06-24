from src.models.document import MetaSummary
from src.services.thin_evidence_gate import check_thin_evidence, strip_overview_grading


def test_zero_docs_is_thin() -> None:
    is_thin, reason = check_thin_evidence([])
    assert is_thin is True
    assert reason is not None
    assert "No core" in reason


def test_one_doc_is_thin() -> None:
    is_thin, reason = check_thin_evidence(["privacy_policy"])
    assert is_thin is True
    assert reason is not None
    assert "1" in reason


def test_two_same_type_docs_are_thin() -> None:
    is_thin, reason = check_thin_evidence(["privacy_policy", "privacy_policy"])
    assert is_thin is True
    assert reason is not None
    assert "1" in reason


def test_two_different_type_docs_are_thin_due_to_count() -> None:
    is_thin, reason = check_thin_evidence(["privacy_policy", "terms_of_service"])
    assert is_thin is True
    assert reason is not None


def test_two_same_type_plus_one_different_is_not_thin() -> None:
    is_thin, reason = check_thin_evidence(["privacy_policy", "privacy_policy", "terms_of_service"])
    assert is_thin is False
    assert reason is None


def test_three_docs_are_not_thin() -> None:
    is_thin, reason = check_thin_evidence(["privacy_policy", "terms_of_service", "cookie_policy"])
    assert is_thin is False
    assert reason is None


def test_non_core_doc_types_are_ignored() -> None:
    is_thin, reason = check_thin_evidence(["community_guidelines", "copyright_policy", "other"])
    assert is_thin is True
    assert reason is not None
    assert "No core" in reason


def test_mixed_core_and_non_core_docs() -> None:
    is_thin, reason = check_thin_evidence(
        ["privacy_policy", "terms_of_service", "cookie_policy", "community_guidelines", "other"]
    )
    assert is_thin is False
    assert reason is None


def test_strip_overview_grading_clears_consumer_scores() -> None:
    meta = MetaSummary.model_validate(
        {
            "summary": "partial",
            "scores": {
                "transparency": {"score": 5, "justification": "ok"},
                "data_collection_scope": {"score": 5, "justification": "ok"},
                "user_control": {"score": 5, "justification": "ok"},
                "third_party_sharing": {"score": 5, "justification": "ok"},
            },
            "grade": "D",
            "verdict": "pervasive",
            "risk_score": 7,
            "grade_justification": "Too harsh for one doc",
        }
    )

    strip_overview_grading(meta)

    assert meta.grade is None
    assert meta.verdict is None
    assert meta.risk_score is None
    assert meta.grade_justification is None
    assert meta.summary == "partial"
