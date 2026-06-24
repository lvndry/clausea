from src.analyzers.signal_consistency import find_signal_prose_contradictions


def test_coinbase_unclear_signal_with_sells_prose_is_contradiction() -> None:
    contradictions = find_signal_prose_contradictions(
        headline="Coinbase sells user identifiers to Meta",
        summary="",
        privacy_signals={"sells_data": "unclear"},
        citations=None,
    )
    assert len(contradictions) == 1
    issue = contradictions[0]
    assert issue["phrase"] == "sells user"
    assert issue["signal_field"] == "sells_data"
    assert issue["signal_value"] == "unclear"
    assert "unclear" in issue["issue"]


def test_signal_no_with_sells_prose_is_contradiction() -> None:
    contradictions = find_signal_prose_contradictions(
        headline="Acme sells your browsing history to data brokers",
        summary="",
        privacy_signals={"sells_data": "no"},
        citations=None,
    )
    assert any(
        c["signal_field"] == "sells_data" and c["signal_value"] == "no" for c in contradictions
    )


def test_signal_yes_with_sells_prose_is_not_contradiction() -> None:
    contradictions = find_signal_prose_contradictions(
        headline="Acme sells your browsing history to data brokers",
        summary="",
        privacy_signals={"sells_data": "yes"},
        citations=None,
    )
    assert contradictions == []


def test_biometric_without_verified_citation_is_unsupported_claim() -> None:
    contradictions = find_signal_prose_contradictions(
        headline="FaceApp collects biometric face templates without deletion rights",
        summary="",
        privacy_signals=None,
        citations=[{"quote": "we process facial data", "verified": False}],
    )
    assert len(contradictions) == 1
    issue = contradictions[0]
    assert issue["phrase"] == "biometric"
    assert issue["signal_field"] is None
    assert issue["signal_value"] is None
    assert "verified citation" in issue["issue"]


def test_biometric_with_verified_citation_is_not_flagged() -> None:
    contradictions = find_signal_prose_contradictions(
        headline="FaceApp collects biometric face templates without deletion rights",
        summary="",
        privacy_signals=None,
        citations=[
            {
                "quote": "We collect biometric identifiers from your photos",
                "verified": True,
            }
        ],
    )
    assert contradictions == []
