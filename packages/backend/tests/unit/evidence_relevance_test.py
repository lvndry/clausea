from src.models.document import EvidenceSpan
from src.services.evidence_relevance import (
    filter_evidence_spans,
    infer_insight_category,
    is_substantive_evidence,
    quote_signals_foreign_topic,
    select_topic_citations,
)


def test_rejects_empty_quotes() -> None:
    assert is_substantive_evidence("", category="data_sharing") is False
    assert is_substantive_evidence("   ", category="retention") is False


def test_keeps_non_empty_quotes_without_keyword_heuristics() -> None:
    quote = "Cookies are small text files placed in device browsers to store preferences."
    assert is_substantive_evidence(quote, category="data_sharing") is True
    assert is_substantive_evidence(quote, category="retention") is True


def test_quote_signals_foreign_topic_is_always_false() -> None:
    quote = "All disputes must be resolved through binding arbitration."
    assert quote_signals_foreign_topic(quote, category="retention") is False
    assert quote_signals_foreign_topic(quote, category="dispute_resolution") is False


def test_infer_insight_category_returns_default() -> None:
    assert infer_insight_category("Binding arbitration / class action waiver") == "dangers"
    assert (
        infer_insight_category(
            "Repeat infringer account termination (DMCA-normal)",
            default="termination_consequences",
        )
        == "termination_consequences"
    )


def test_filter_evidence_spans_drops_empty_and_dedupes() -> None:
    spans = [
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="",
        ),
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="We share account data with service providers who assist our operations.",
        ),
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="We share account data with service providers who assist our operations.",
        ),
    ]
    filtered = filter_evidence_spans(
        spans,
        category="data_sharing",
        finding_value="Service providers",
    )
    assert len(filtered) == 1
    assert "share account data" in filtered[0].quote


def test_filter_evidence_spans_prefers_verified_spans() -> None:
    spans = [
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="Unverified quote text.",
        ),
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="Verified quote text.",
            start_char=10,
            end_char=30,
        ),
    ]
    filtered = filter_evidence_spans(
        spans,
        category="data_sharing",
        finding_value="Partners",
    )
    assert filtered[0].quote == "Verified quote text."
    assert filtered[0].verified is True


def test_select_topic_citations_limits_results() -> None:
    spans = [
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote=f"We retain account data for {index} days after deletion.",
        )
        for index in range(6)
    ]
    selected = select_topic_citations(
        spans,
        category="retention",
        finding_value="Account data retention",
    )
    assert len(selected) == 5
