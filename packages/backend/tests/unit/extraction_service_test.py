from src.services.extraction_service import (
    _chunk_text,
    _clean_sharing_rights_raw,
    _resolve_quote_offsets,
)


def test_chunk_text_single_chunk_when_short() -> None:
    text = "hello world"
    chunks = _chunk_text(text, chunk_size=100, overlap=10)
    assert chunks == [text]


def test_chunk_text_produces_overlap() -> None:
    text = "abcdefghijklmnopqrstuvwxyz"  # 26 chars
    chunks = _chunk_text(text, chunk_size=10, overlap=3)
    # Expect:
    # chunk1: 0..10  -> abcdefghij
    # chunk2: 7..17  -> hijklmnopq
    assert chunks[0] == "abcdefghij"
    assert chunks[1].startswith("hij")
    assert len(chunks) >= 2


def test_resolve_quote_offsets_exact_match() -> None:
    haystack = "A quick brown fox jumps over the lazy dog."
    quote = "brown fox jumps"
    start, end = _resolve_quote_offsets(haystack, quote)
    assert start is not None and end is not None
    assert haystack[start:end] == quote


def test_resolve_quote_offsets_not_found() -> None:
    haystack = "A quick brown fox"
    quote = "missing quote"
    start, end = _resolve_quote_offsets(haystack, quote)
    assert start is None
    assert end is None


def test_clean_sharing_rights_raw_fixes_empty_list_risk_level() -> None:
    """Test that _clean_sharing_rights_raw converts empty list risk_level to None."""
    raw = {
        "third_party_details": [
            {
                "recipient": "Test",
                "data_shared": ["email"],
                "purpose": "test",
                "risk_level": [],
                "quote": "test",
            },
            {
                "recipient": "Test2",
                "data_shared": ["phone"],
                "purpose": "test2",
                "risk_level": "high",
                "quote": "test2",
            },
        ]
    }

    cleaned = _clean_sharing_rights_raw(raw)

    # First item should have risk_level converted from [] to None
    assert cleaned["third_party_details"][0]["risk_level"] is None
    # Second item should remain unchanged
    assert cleaned["third_party_details"][1]["risk_level"] == "high"


def test_clean_sharing_rights_raw_handles_non_string_risk_level() -> None:
    """Test that _clean_sharing_rights_raw converts non-string risk_level to string."""
    raw = {
        "third_party_details": [
            {
                "recipient": "Test",
                "data_shared": ["email"],
                "purpose": "test",
                "risk_level": 42,
                "quote": "test",
            },
        ]
    }

    cleaned = _clean_sharing_rights_raw(raw)

    assert cleaned["third_party_details"][0]["risk_level"] == "42"


def test_clean_sharing_rights_raw_ignores_valid_data() -> None:
    """Test that _clean_sharing_rights_raw leaves valid data unchanged."""
    raw = {
        "third_party_details": [
            {
                "recipient": "Test",
                "data_shared": ["email"],
                "purpose": "test",
                "risk_level": "medium",
                "quote": "test",
            },
        ],
        "your_rights": [{"value": "test", "quote": "test"}],
    }

    cleaned = _clean_sharing_rights_raw(raw)

    assert cleaned == raw
