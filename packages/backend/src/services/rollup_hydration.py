"""Hydrate slim rollups with evidence from document extractions."""

from __future__ import annotations

from src.models.document import Document, EvidenceSpan, InsightCategory
from src.models.finding import AggregatedFinding, Aggregation, Finding, FindingConflict
from src.models.product_intelligence import ProductRollup
from src.services.aggregation_service import AggregationService
from src.services.evidence_relevance import filter_evidence_spans


def _normalize(value: str) -> str:
    return AggregationService._normalize_value(value)


def _findings_for_documents(documents: list[Document], product_id: str) -> list[Finding]:
    service = AggregationService.__new__(AggregationService)
    findings: list[Finding] = []
    for doc in documents:
        if not doc.extraction:
            continue
        findings.extend(
            service._extraction_to_findings(
                product_id=product_id,
                document_id=doc.id,
                extraction=doc.extraction,
            )
        )
    return findings


def _evidence_for_item(
    findings: list[Finding],
    *,
    category: InsightCategory,
    value: str,
    document_ids: list[str],
) -> list[EvidenceSpan]:
    normalized = _normalize(value)
    allowed = set(document_ids)
    evidence: list[EvidenceSpan] = []
    for finding in findings:
        if finding.category != category:
            continue
        if finding.document_id not in allowed:
            continue
        if (finding.normalized_value or _normalize(finding.value)) != normalized:
            continue
        evidence.extend(finding.evidence)
    return filter_evidence_spans(evidence, category=category, finding_value=value)


def rollup_to_aggregation(
    *,
    product_id: str,
    product_slug: str,
    rollup: ProductRollup,
    documents: list[Document],
) -> Aggregation:
    """Convert stored slim rollup to Aggregation with hydrated evidence."""
    findings = _findings_for_documents(documents, product_id)
    aggregated: list[AggregatedFinding] = []
    for item in rollup.items:
        evidence = _evidence_for_item(
            findings,
            category=item.category,
            value=item.value,
            document_ids=item.document_ids,
        )
        aggregated.append(
            AggregatedFinding(
                category=item.category,
                value=item.value,
                documents=item.document_ids,
                evidence=evidence,
                attributes=item.attributes,
                confidence=item.confidence,
            )
        )

    conflicts: list[FindingConflict] = []
    for conflict in rollup.conflicts:
        category_findings = [f for f in findings if f.category == conflict.category]
        conflict_values = {
            f.normalized_value or _normalize(f.value)
            for f in category_findings
            if f.document_id in conflict.document_ids
        }
        evidence: list[EvidenceSpan] = []
        if len(conflict_values) > 1:
            for finding in category_findings:
                if finding.document_id in conflict.document_ids:
                    evidence.extend(finding.evidence)
        conflicts.append(
            FindingConflict(
                category=conflict.category,
                description=conflict.description,
                document_ids=conflict.document_ids,
                evidence=filter_evidence_spans(
                    evidence, category=conflict.category, finding_value=conflict.description
                ),
                severity=conflict.severity,
            )
        )

    return Aggregation(
        product_id=product_id,
        product_slug=product_slug,
        coverage=rollup.coverage,
        findings=aggregated,
        conflicts=conflicts,
        generated_at=rollup.generated_at,
    )
