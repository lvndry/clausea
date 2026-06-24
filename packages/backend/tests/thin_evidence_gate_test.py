from src.services.thin_evidence_gate import check_thin_evidence


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


def test_two_different_type_docs_are_not_thin() -> None:
    is_thin, reason = check_thin_evidence(["privacy_policy", "terms_of_service"])
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
        ["privacy_policy", "terms_of_service", "community_guidelines", "other"]
    )
    assert is_thin is False
    assert reason is None
