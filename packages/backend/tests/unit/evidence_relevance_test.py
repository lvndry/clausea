from src.models.document import EvidenceSpan
from src.services.evidence_relevance import (
    filter_evidence_spans,
    infer_insight_category,
    is_substantive_evidence,
    quote_signals_foreign_topic,
    select_topic_citations,
)


def test_rejects_cookie_definition_boilerplate() -> None:
    quote = "Cookies are small text files placed in device browsers to store preferences."
    assert is_substantive_evidence(quote, category="data_sharing") is False
    assert is_substantive_evidence(quote, category="retention") is False


def test_rejects_cookie_opt_out_mechanics_for_non_cookie_topics() -> None:
    quote = "Please note that cookie-based opt-outs are not effective on mobile applications."
    assert is_substantive_evidence(quote, category="data_sharing") is False
    assert is_substantive_evidence(quote, category="ai_training") is False


def test_rejects_manage_cookies_footer_text() -> None:
    quote = "Use our EU cookie consent tool or the Manage cookies link in the footer."
    assert is_substantive_evidence(quote, category="data_collection") is False


def test_rejects_foreign_topic_quotes_for_data_topics() -> None:
    assert (
        is_substantive_evidence(
            "Repeat infringer accounts may be terminated without notice.",
            category="retention",
            finding_value="Account data: 30 days",
        )
        is False
    )
    assert (
        is_substantive_evidence(
            "This agreement is personal to you and non-assignable.",
            category="ai_training",
            finding_value="We do not train on user prompts.",
        )
        is False
    )
    assert (
        is_substantive_evidence(
            "Disputes will be resolved by binding arbitration with a class action waiver.",
            category="data_collection",
            finding_value="Email address",
        )
        is False
    )


def test_quote_signals_foreign_topic_detects_arbitration() -> None:
    quote = "All disputes must be resolved through binding arbitration."
    assert quote_signals_foreign_topic(quote, category="retention") is True
    assert quote_signals_foreign_topic(quote, category="dispute_resolution") is False


def test_keeps_substantive_sharing_quote() -> None:
    quote = "We may share your personal information with advertising partners for targeted ads."
    assert is_substantive_evidence(quote, category="data_sharing", finding_value="Advertisers")


def test_keeps_named_tracker_for_cookie_topic() -> None:
    quote = "We use Google Analytics cookies to measure site usage across sessions."
    assert is_substantive_evidence(
        quote,
        category="cookies_tracking",
        finding_value="Google Analytics",
    )


def test_filter_evidence_spans_preserves_relevant_quotes() -> None:
    spans = [
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="Cookies are small text files placed in your browser.",
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


def test_infer_insight_category_routes_routine_legal_terms() -> None:
    assert (
        infer_insight_category("Binding arbitration / class action waiver") == "dispute_resolution"
    )
    assert (
        infer_insight_category("Repeat infringer account termination (DMCA-normal)")
        == "termination_consequences"
    )
    assert infer_insight_category("Non-assignable agreement clause") == "content_ownership"


def test_dangers_rejects_foreign_topic_in_finding_value() -> None:
    quote = "You agree to resolve disputes individually through binding arbitration."
    assert (
        is_substantive_evidence(
            quote,
            category="dangers",
            finding_value="Binding arbitration / class action waiver",
        )
        is False
    )


def test_select_topic_citations_limits_and_ranks() -> None:
    spans = [
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="We retain account data for 30 days after deletion.",
        ),
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="Additional disclosure for enterprise plans.",
        ),
        EvidenceSpan(
            document_id="doc_1",
            url="https://example.com/privacy",
            quote="We store profile information until you delete your account.",
        ),
    ]
    selected = select_topic_citations(
        spans,
        category="retention",
        finding_value="Account data: 30 days",
        limit=2,
    )
    assert len(selected) == 2
    assert all("retain" in span.quote.lower() or "store" in span.quote.lower() for span in selected)


def test_select_topic_citations_default_limit_is_five() -> None:
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
