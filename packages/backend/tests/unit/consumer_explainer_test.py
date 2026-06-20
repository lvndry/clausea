"""Unit tests for the consumer TOS-explainer subsystem.

Covers the load-bearing server-side guarantees the finalized prompt depends on:
  - the grade clamp (1 critical -> max D, 2+ -> max E),
  - quote de-citation (a quote absent from the extraction is dropped to
    quote_status="none" while the finding itself is kept),
  - lenient enum/coercion for weak-model drift,
  - the surgical $set persistence path (matched_count semantics).

The LLM is always mocked — no real network or DB calls.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import ModelResponse

from src.analyser import (
    _validate_consumer_explainer,
    _validate_consumer_explainer_quotes,
    enrich_consumer_explainer_citations,
    generate_consumer_explainer,
)
from src.models.document import (
    ConsumerCase,
    ConsumerExplainer,
    Document,
    DocumentExtraction,
    EvidenceSpan,
    ExtractedDataItem,
    SourceCitation,
)
from src.repositories.document_repository import DocumentRepository


def _extraction_with_quotes(*quotes: str) -> DocumentExtraction:
    """Build a minimal extraction whose data items carry the given evidence quotes."""
    data_items = [
        ExtractedDataItem(
            data_type=f"data_{index}",
            evidence=[
                EvidenceSpan(
                    document_id="doc-1",
                    url="https://example.com/policy",
                    quote=quote,
                    start_char=0,
                    end_char=len(quote),
                    verified=True,
                )
            ],
        )
        for index, quote in enumerate(quotes)
    ]
    return DocumentExtraction(source_content_hash="hash-1", data_collected=data_items)


def _make_response(content: str, model: str = "openrouter/gemini-2.5-flash") -> ModelResponse:
    response = MagicMock(spec=ModelResponse)
    response.model = model
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


def _make_document(extraction: DocumentExtraction | None) -> Document:
    return Document(
        id="doc-1",
        url="https://example.com/policy",
        product_id="prod-1",
        doc_type="privacy_policy",
        title="Privacy Policy",
        markdown="# policy",
        text="policy body",
        extraction=extraction,
        created_at=datetime(2026, 1, 1),
    )


# ---------------------------------------------------------------------------
# Grade clamp
# ---------------------------------------------------------------------------


def test_grade_clamp_one_critical_caps_at_d() -> None:
    extraction = _extraction_with_quotes("we sell your data")
    explainer = ConsumerExplainer(
        grade="A",
        watch_out_for=[
            ConsumerCase(title="Sells your data", severity="critical"),
        ],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert validated.critical_findings_count == 1
    assert validated.grade == "D"


def test_grade_clamp_two_criticals_caps_at_e() -> None:
    extraction = _extraction_with_quotes("we sell your data", "we train AI on your data")
    explainer = ConsumerExplainer(
        grade="B",
        watch_out_for=[ConsumerCase(title="Sells your data", severity="critical")],
        who_gets_your_data=[ConsumerCase(title="Ad networks", severity="critical")],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert validated.critical_findings_count == 2
    assert validated.grade == "E"


def test_grade_clamp_does_not_improve_a_worse_grade() -> None:
    """The clamp only lowers; a model that self-rated E with one critical stays E."""
    extraction = _extraction_with_quotes("we sell your data")
    explainer = ConsumerExplainer(
        grade="E",
        watch_out_for=[ConsumerCase(title="Sells your data", severity="critical")],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert validated.grade == "E"


def test_grade_clamp_blocker_classification_counts_as_critical() -> None:
    extraction = _extraction_with_quotes("we sell your personal information")
    explainer = ConsumerExplainer(
        grade="A",
        watch_out_for=[
            ConsumerCase(title="Sells data", severity="critical", classification="blocker"),
        ],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert validated.critical_findings_count == 1
    assert validated.grade == "D"


def test_arbitration_blocker_is_downgraded_not_critical() -> None:
    extraction = _extraction_with_quotes("binding arbitration and class action waiver")
    explainer = ConsumerExplainer(
        grade="A",
        watch_out_for=[
            ConsumerCase(
                title="Binding arbitration",
                severity="critical",
                classification="blocker",
                means_for_you="You must arbitrate disputes instead of going to court.",
            ),
        ],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert len(validated.watch_out_for) == 1
    assert validated.watch_out_for[0].severity == "medium"
    assert validated.critical_findings_count == 0
    assert validated.grade == "A"


def test_repeat_infringer_removed_from_watch_out_for() -> None:
    extraction = _extraction_with_quotes(
        "We may terminate accounts of repeat infringers under our DMCA policy."
    )
    explainer = ConsumerExplainer(
        grade="D",
        watch_out_for=[
            ConsumerCase(
                title="Repeat infringer termination",
                severity="high",
                means_for_you="Your account may be disabled for repeated copyright infringement.",
            ),
        ],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert validated.watch_out_for == []
    assert validated.critical_findings_count == 0
    assert validated.grade == "D"


def test_no_critical_leaves_grade_untouched() -> None:
    extraction = _extraction_with_quotes("we collect your email")
    explainer = ConsumerExplainer(
        grade="B",
        watch_out_for=[ConsumerCase(title="Collects email", severity="medium")],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert validated.critical_findings_count == 0
    assert validated.grade == "B"


def test_good_to_know_boosts_grade_when_no_criticals() -> None:
    extraction = _extraction_with_quotes("we encrypt data at rest")
    explainer = ConsumerExplainer(
        grade="C",
        good_to_know=["End-to-end encryption for messages", "30-day data deletion on request"],
        watch_out_for=[ConsumerCase(title="Collects email", severity="medium")],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert validated.critical_findings_count == 0
    assert validated.grade == "B"


# ---------------------------------------------------------------------------
# Quote de-citation
# ---------------------------------------------------------------------------


def test_quote_present_in_extraction_is_kept_and_cited() -> None:
    extraction = _extraction_with_quotes("We may sell your personal information to advertisers.")
    explainer = ConsumerExplainer(
        watch_out_for=[
            ConsumerCase(
                title="Sells data",
                severity="high",
                quote="sell your personal information",
                quote_status="from_extraction",
            )
        ],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    case = validated.watch_out_for[0]
    assert case.quote == "sell your personal information"
    assert case.quote_status == "from_extraction"


def test_verified_quote_attaches_source_citation_metadata() -> None:
    extraction = _extraction_with_quotes("We may sell your personal information to advertisers.")
    document = _make_document(extraction)
    explainer = ConsumerExplainer(
        watch_out_for=[
            ConsumerCase(
                title="Sells data",
                severity="high",
                quote="sell your personal information",
                quote_status="from_extraction",
            )
        ],
    )

    validated = _validate_consumer_explainer(explainer, extraction, document)

    citation = validated.watch_out_for[0].citation
    assert citation is not None
    assert len(validated.watch_out_for[0].citations) == 1
    assert citation.document_id == "doc-1"
    assert citation.document_title == "Privacy Policy"
    assert citation.document_type == "privacy_policy"
    assert citation.document_url == "https://example.com/policy"
    assert citation.quote == "We may sell your personal information to advertisers."


def test_enrich_consumer_explainer_backfills_missing_citations() -> None:
    extraction = _extraction_with_quotes("We may sell your personal information to advertisers.")
    document = _make_document(extraction)
    explainer = ConsumerExplainer(
        watch_out_for=[
            ConsumerCase(
                title="Sells data",
                severity="high",
                quote="sell your personal information",
                quote_status="from_extraction",
                citation=None,
            )
        ],
    )

    enriched = enrich_consumer_explainer_citations(explainer, [document])

    case = enriched.watch_out_for[0]
    assert case.citation is not None
    assert len(case.citations) == 1
    assert case.citation.document_title == "Privacy Policy"
    assert case.citation.document_url == "https://example.com/policy"


def test_enrich_consumer_explainer_backfills_all_matching_source_documents() -> None:
    shared_quote = "customer content for model training"
    privacy_extraction = DocumentExtraction(
        source_content_hash="hash-privacy",
        data_collected=[
            ExtractedDataItem(
                data_type="ai_training",
                evidence=[
                    EvidenceSpan(
                        document_id="doc-privacy",
                        url="https://example.com/privacy",
                        quote=f"We may use {shared_quote} to improve our services.",
                        start_char=0,
                        end_char=64,
                        verified=True,
                    )
                ],
            )
        ],
    )
    terms_extraction = DocumentExtraction(
        source_content_hash="hash-terms",
        data_collected=[
            ExtractedDataItem(
                data_type="ai_training",
                evidence=[
                    EvidenceSpan(
                        document_id="doc-terms",
                        url="https://example.com/terms",
                        quote=f"We may use {shared_quote}.",
                        start_char=0,
                        end_char=44,
                        verified=True,
                    )
                ],
            )
        ],
    )
    documents = [
        Document(
            id="doc-privacy",
            url="https://example.com/privacy",
            product_id="prod-1",
            doc_type="privacy_policy",
            title="Privacy Policy",
            markdown="# privacy",
            text="privacy body",
            extraction=privacy_extraction,
            created_at=datetime(2026, 1, 1),
        ),
        Document(
            id="doc-terms",
            url="https://example.com/terms",
            product_id="prod-1",
            doc_type="terms_of_service",
            title="Terms of Service",
            markdown="# terms",
            text="terms body",
            extraction=terms_extraction,
            created_at=datetime(2026, 1, 1),
        ),
    ]
    explainer = ConsumerExplainer(
        watch_out_for=[
            ConsumerCase(
                title="AI training",
                severity="critical",
                quote=shared_quote,
                quote_status="from_extraction",
            )
        ],
    )

    enriched = enrich_consumer_explainer_citations(explainer, documents)

    matched = enriched.watch_out_for[0].citations
    assert len(matched) == 2
    assert {citation.document_id for citation in matched} == {
        "doc-privacy",
        "doc-terms",
    }


def test_product_rollup_quote_resolves_to_matching_source_document() -> None:
    explainer = ConsumerExplainer(
        watch_out_for=[
            ConsumerCase(
                title="AI training",
                severity="critical",
                quote="customer content for model training",
                quote_status="from_extraction",
            )
        ],
    )
    citations = [
        SourceCitation(
            document_id="doc-privacy",
            document_title="Privacy Policy",
            document_type="privacy_policy",
            document_url="https://example.com/privacy",
            quote="We collect your email address.",
        ),
        SourceCitation(
            document_id="doc-terms",
            document_title="Terms of Service",
            document_type="terms_of_service",
            document_url="https://example.com/terms",
            quote="We may use customer content for model training.",
        ),
    ]

    validated = _validate_consumer_explainer_quotes(explainer, citations)

    matched = validated.watch_out_for[0].citations
    assert len(matched) == 1
    citation = matched[0]
    assert citation.document_id == "doc-terms"
    assert citation.document_title == "Terms of Service"
    assert validated.watch_out_for[0].quote_status == "from_extraction"
    assert validated.watch_out_for[0].citation == citation


def test_product_rollup_quote_resolves_to_all_matching_source_documents() -> None:
    shared_quote = "customer content for model training"
    explainer = ConsumerExplainer(
        watch_out_for=[
            ConsumerCase(
                title="AI training",
                severity="critical",
                quote=shared_quote,
                quote_status="from_extraction",
            )
        ],
    )
    citations = [
        SourceCitation(
            document_id="doc-privacy",
            document_title="Privacy Policy",
            document_type="privacy_policy",
            document_url="https://example.com/privacy",
            quote=f"We may use {shared_quote} to improve our services.",
        ),
        SourceCitation(
            document_id="doc-terms",
            document_title="Terms of Service",
            document_type="terms_of_service",
            document_url="https://example.com/terms",
            quote=f"We may use {shared_quote}.",
        ),
    ]

    validated = _validate_consumer_explainer_quotes(explainer, citations)

    matched = validated.watch_out_for[0].citations
    assert len(matched) == 2
    assert {citation.document_id for citation in matched} == {
        "doc-privacy",
        "doc-terms",
    }
    assert validated.watch_out_for[0].citation == matched[0]


def test_quote_absent_from_extraction_is_decited_but_finding_kept() -> None:
    extraction = _extraction_with_quotes("We collect your email address.")
    explainer = ConsumerExplainer(
        watch_out_for=[
            ConsumerCase(
                title="Invented danger",
                severity="high",
                quote="We will sell your data to insurers who raise your rates.",
                quote_status="from_extraction",
            )
        ],
    )

    validated = _validate_consumer_explainer(explainer, extraction)

    assert len(validated.watch_out_for) == 1  # finding kept, not dropped
    case = validated.watch_out_for[0]
    assert case.quote is None
    assert case.quote_status == "none"


# ---------------------------------------------------------------------------
# Lenient enum / bool coercion
# ---------------------------------------------------------------------------


def test_lenient_severity_synonym_coercion() -> None:
    case = ConsumerCase(title="x", severity="severe")
    assert case.severity == "critical"
    assert ConsumerCase(title="x", severity="MAJOR").severity == "high"
    assert ConsumerCase(title="x", severity="garbage").severity == "medium"


def test_lenient_grade_and_count_coercion() -> None:
    explainer = ConsumerExplainer.model_validate(
        {
            "grade": "d (user-hostile)",
            "critical_findings_count": "2",
            "confidence": "VERY-LOW",
        }
    )
    assert explainer.grade == "D"
    assert explainer.critical_findings_count == 2
    assert explainer.confidence == "medium"  # unknown confidence falls back


def test_quote_status_coercion_defaults_to_none() -> None:
    assert ConsumerCase(title="x", quote_status="exact").quote_status == "none"
    assert ConsumerCase(title="x", quote_status="from_extraction").quote_status == "from_extraction"


def test_typed_list_aliases_who_and_data() -> None:
    """The shared ConsumerCase accepts the who/data aliases the prompt schema emits."""
    explainer = ConsumerExplainer.model_validate(
        {
            "who_gets_your_data": [{"who": "Google Analytics", "what_they_get": "activity"}],
            "what_they_collect": [{"data": "your location", "why": "ads"}],
        }
    )
    assert explainer.who_gets_your_data[0].title == "Google Analytics"
    assert explainer.what_they_collect[0].title == "your location"
    assert explainer.what_they_collect[0].why == "ads"


# ---------------------------------------------------------------------------
# generate_consumer_explainer — mocked LLM end to end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_consumer_explainer_parses_and_clamps() -> None:
    extraction = _extraction_with_quotes("We sell your personal information to partners.")
    document = _make_document(extraction)

    model_output = {
        "headline": "This app sells your data.",
        "tl_dr": "They sell your data. Opt out in settings.",
        "grade": "A",  # over-optimistic; the clamp must lower it
        "grade_reason": "sells data",
        "critical_findings_count": 0,  # wrong; recomputed server-side
        "confidence": "high",
        "watch_out_for": [
            {
                "title": "Sells your data",
                "means_for_you": "Other companies get your info.",
                "severity": "critical",
                "quote": "sell your personal information",
                "quote_status": "from_extraction",
            }
        ],
    }
    response = _make_response(json.dumps(model_output))

    with patch(
        "src.analyser.acompletion_with_fallback",
        new=AsyncMock(return_value=response),
    ):
        explainer = await generate_consumer_explainer(document)

    assert explainer is not None
    assert explainer.critical_findings_count == 1
    assert explainer.grade == "D"  # clamped from A
    assert explainer.watch_out_for[0].quote == "sell your personal information"


@pytest.mark.asyncio
async def test_generate_consumer_explainer_strips_code_fences() -> None:
    extraction = _extraction_with_quotes("We collect your email address.")
    document = _make_document(extraction)
    fenced = "```json\n" + json.dumps({"headline": "h", "grade": "C"}) + "\n```"
    response = _make_response(fenced)

    with patch(
        "src.analyser.acompletion_with_fallback",
        new=AsyncMock(return_value=response),
    ):
        explainer = await generate_consumer_explainer(document)

    assert explainer is not None
    assert explainer.headline == "h"


@pytest.mark.asyncio
async def test_generate_consumer_explainer_returns_none_without_extraction() -> None:
    document = _make_document(None)
    with patch(
        "src.analyser.acompletion_with_fallback",
        new=AsyncMock(side_effect=AssertionError("LLM must not be called without extraction")),
    ):
        result = await generate_consumer_explainer(document)
    assert result is None


@pytest.mark.asyncio
async def test_generate_consumer_explainer_returns_none_on_persistent_parse_failure() -> None:
    extraction = _extraction_with_quotes("We collect your email address.")
    document = _make_document(extraction)
    response = _make_response("not valid json at all")

    with patch(
        "src.analyser.acompletion_with_fallback",
        new=AsyncMock(return_value=response),
    ):
        result = await generate_consumer_explainer(document, max_retries=2)

    assert result is None


# ---------------------------------------------------------------------------
# Surgical persistence path
# ---------------------------------------------------------------------------


def _fake_db_for_update(matched: int) -> tuple[Any, AsyncMock]:
    documents_collection = AsyncMock()
    update_result = MagicMock()
    update_result.matched_count = matched
    documents_collection.update_one = AsyncMock(return_value=update_result)
    db = AsyncMock()
    db.documents = documents_collection
    return db, documents_collection.update_one


@pytest.mark.asyncio
async def test_update_consumer_explainer_surgical_set() -> None:
    repo = DocumentRepository()
    db, update_one = _fake_db_for_update(matched=1)
    explainer = ConsumerExplainer(headline="h", grade="D")

    success = await repo.update_consumer_explainer(db, "doc-1", explainer)

    assert success is True
    update_one.assert_awaited_once()
    call_args = update_one.await_args
    assert call_args is not None
    assert call_args.args[0] == {"id": "doc-1"}
    set_payload = call_args.args[1]["$set"]
    assert set_payload["consumer_explainer"]["headline"] == "h"
    assert set_payload["consumer_explainer"]["grade"] == "D"
    assert "updated_at" in set_payload
    # Only the explainer + timestamp are touched — no other document fields.
    assert set(set_payload.keys()) == {"consumer_explainer", "updated_at"}


@pytest.mark.asyncio
async def test_update_consumer_explainer_reports_false_when_no_match() -> None:
    repo = DocumentRepository()
    db, _update_one = _fake_db_for_update(matched=0)
    explainer = ConsumerExplainer(headline="h")

    success = await repo.update_consumer_explainer(db, "missing-doc", explainer)

    assert success is False


@pytest.mark.asyncio
async def test_repository_update_guards_explainer_against_none_wipe() -> None:
    """update() must not null a stored consumer_explainer with an incoming None."""
    repo = DocumentRepository()
    documents_collection = AsyncMock()
    documents_collection.find_one = AsyncMock(
        return_value={
            "id": "doc-1",
            "text": "real text",
            "markdown": "# real",
            "consumer_explainer": {"headline": "stored"},
        }
    )
    update_result = MagicMock()
    update_result.matched_count = 1
    update_result.modified_count = 1
    documents_collection.update_one = AsyncMock(return_value=update_result)
    db = AsyncMock()
    db.documents = documents_collection

    partial_doc = Document(
        id="doc-1",
        url="https://example.com/policy",
        product_id="prod-1",
        doc_type="privacy_policy",
        markdown="",
        text="",
        consumer_explainer=None,
        created_at=datetime(2026, 1, 1),
    )

    await repo.update(db, partial_doc)

    await_args = documents_collection.update_one.await_args
    assert await_args is not None
    set_payload = await_args.args[1]["$set"]
    assert "consumer_explainer" not in set_payload  # guarded out
    assert "text" not in set_payload
    assert "markdown" not in set_payload
