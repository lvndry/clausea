"""Build product-level topic reports with citations from aggregations."""

from __future__ import annotations

from src.models.document import DocumentSummary, EvidenceSpan, InsightCategory
from src.models.finding import Aggregation
from src.models.topic_report import (
    ProductTopicReport,
    TopicCitation,
    TopicConflict,
    TopicFinding,
    TopicReportItem,
)
from src.services.evidence_relevance import TOPIC_CITATION_LIMIT, select_topic_citations
from src.services.topic_stance_service import evaluate_topic_stances
from src.utils.standard_terms import finding_materiality_label, should_exclude_from_dangers


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Return values with duplicates removed while preserving first-seen order."""
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _evidence_key(evidence: EvidenceSpan) -> tuple:
    return (
        evidence.document_id,
        (evidence.quote or "").strip(),
        evidence.start_char,
        evidence.end_char,
        evidence.section_title or "",
        evidence.url or "",
    )


def _build_citations(
    evidence_spans: list[EvidenceSpan],
    documents_by_id: dict[str, DocumentSummary],
    *,
    category: InsightCategory,
    finding_value: str | None = None,
) -> list[TopicCitation]:
    selected_spans = select_topic_citations(
        evidence_spans,
        category=category,
        finding_value=finding_value,
        limit=TOPIC_CITATION_LIMIT,
    )
    seen: set[tuple] = set()
    citations: list[TopicCitation] = []
    for evidence in selected_spans:
        if not (evidence.quote or "").strip():
            continue
        key = _evidence_key(evidence)
        if key in seen:
            continue
        seen.add(key)
        source_doc = documents_by_id.get(evidence.document_id)
        citations.append(
            TopicCitation(
                document_id=evidence.document_id,
                document_title=source_doc.title if source_doc else None,
                document_url=source_doc.url if source_doc else evidence.url,
                quote=evidence.quote,
                section_title=evidence.section_title,
                verified=evidence.verified,
            )
        )
    return citations


def build_product_topic_report(
    *, product_slug: str, aggregation: Aggregation, documents: list[DocumentSummary]
) -> ProductTopicReport:
    """Build per-topic output from stored aggregation + document metadata."""
    documents_by_id = {document.id: document for document in documents}

    topics_by_category: dict[InsightCategory, TopicReportItem] = {}

    if aggregation.coverage:
        for item in aggregation.coverage:
            topics_by_category[item.category] = TopicReportItem(
                topic=item.category,
                coverage_status=item.status,
            )

    stance_rows = evaluate_topic_stances(
        findings=aggregation.findings,
        conflicts=aggregation.conflicts,
        coverage=aggregation.coverage,
    )

    for finding in aggregation.findings:
        if finding.category == "dangers" and should_exclude_from_dangers(
            finding.value, materiality=finding_materiality_label(finding.attributes)
        ):
            continue

        if finding.category not in topics_by_category:
            topics_by_category[finding.category] = TopicReportItem(
                topic=finding.category,
                coverage_status="found",
                status="found",
                stance="moderate_risk",
                topic_score=5,
            )

        topic_item = topics_by_category[finding.category]
        if topic_item.coverage_status in {"missing", "not_analyzed"}:
            topic_item.coverage_status = "found"

        citations = _build_citations(
            finding.evidence,
            documents_by_id,
            category=finding.category,
            finding_value=finding.value,
        )
        if not citations:
            # Keep contract strict: emitted findings must be evidence-backed.
            continue
        finding_document_ids = _dedupe_preserve_order(
            list(finding.documents)
            + [citation.document_id for citation in citations if citation.document_id]
        )
        topic_item.findings.append(
            TopicFinding(
                value=finding.value,
                document_ids=finding_document_ids,
                attributes=finding.attributes,
                citations=citations,
            )
        )

    for conflict in aggregation.conflicts:
        if conflict.category not in topics_by_category:
            topics_by_category[conflict.category] = TopicReportItem(
                topic=conflict.category,
                coverage_status="ambiguous",
                status="ambiguous",
                stance="mixed",
                topic_score=6,
            )
        topic_item = topics_by_category[conflict.category]
        topic_item.coverage_status = "ambiguous"

        citations = _build_citations(
            conflict.evidence,
            documents_by_id,
            category=conflict.category,
            finding_value=conflict.description,
        )
        conflict_document_ids = _dedupe_preserve_order(
            list(conflict.document_ids)
            + [citation.document_id for citation in citations if citation.document_id]
        )
        topic_item.conflicts.append(
            TopicConflict(
                description=conflict.description,
                severity=conflict.severity,
                document_ids=conflict_document_ids,
                citations=citations,
            )
        )

    for topic, item in topics_by_category.items():
        row = stance_rows.get(topic)
        if row is None:
            continue
        item.status = row["status"]
        item.stance = row["stance"]
        item.topic_score = row["topic_score"]
        item.rationale = row["rationale"]
        item.rationale_key = row.get("rationale_key")
        item.rationale_params = row.get("rationale_params")

    for item in topics_by_category.values():
        if item.status == "found" and not item.findings and not item.conflicts:
            item.status = "not_disclosed"
            item.stance = "not_disclosed"
            item.topic_score = None
            item.rationale = "Topic lacks verifiable citation evidence."
            item.rationale_key = "topic.missing_verifiable_citation"
            item.rationale_params = None
        item.findings.sort(key=lambda finding: finding.value)
        item.conflicts.sort(key=lambda conflict: conflict.description)

    return ProductTopicReport(
        product_slug=product_slug,
        generated_at=aggregation.generated_at,
        topics=sorted(topics_by_category.values(), key=lambda item: item.topic),
    )
