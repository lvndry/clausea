from src.services.extraction_service import _chunk_text, _resolve_quote_offsets


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
