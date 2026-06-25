from src.models.document import Document
from src.services.extraction_service import _chunk_text, _plan_extraction_segments
from src.utils.quotes import resolve_quote_offsets


def _doc() -> Document:
    return Document(
        url="https://example.com/privacy",
        product_id="p1",
        doc_type="privacy_policy",
        markdown="",
    )


def test_chunk_text_single_chunk_when_short() -> None:
    text = "hello world"
    chunks = _chunk_text(text, chunk_size=100, overlap=10)
    assert chunks == [text]


def test_chunk_text_produces_overlap() -> None:
    text = "abcdefghijklmnopqrstuvwxyz"  # 26 chars
    chunks = _chunk_text(text, chunk_size=10, overlap=3)
    assert chunks[0] == "abcdefghij"
    assert len(chunks) >= 2


def test_plan_extraction_segments_single_segment_for_short_doc() -> None:
    text = "We collect email addresses for account creation.\n" * 500
    segments = _plan_extraction_segments(_doc(), text)
    assert len(segments) == 1
    assert segments[0] == text


def test_plan_extraction_segments_splits_long_doc() -> None:
    # ~1.2M chars ≈ 300K tokens — above the per-segment budget.
    text = "x" * 1_200_000
    segments = _plan_extraction_segments(_doc(), text)
    assert len(segments) > 1


def test_plan_extraction_segments_respects_markdown_sections() -> None:
    section = "## Data retention\nWe keep logs for 90 days.\n\n"
    text = section * 200
    segments = _plan_extraction_segments(_doc(), text)
    assert segments
    assert all("Data retention" in segment for segment in segments)


def test_resolve_quote_offsets_exact_match() -> None:
    haystack = "A quick brown fox jumps over the lazy dog."
    quote = "brown fox jumps"
    start, end, verified = resolve_quote_offsets(haystack, quote)
    assert start is not None and end is not None
    assert haystack[start:end] == quote
    assert verified is True


def test_resolve_quote_offsets_not_found() -> None:
    haystack = "A quick brown fox"
    quote = "missing quote"
    start, end, verified = resolve_quote_offsets(haystack, quote)
    assert start is None
    assert end is None
    assert verified is False
