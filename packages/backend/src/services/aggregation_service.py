"""Aggregation service for merging findings across documents."""

from __future__ import annotations

import re
from collections.abc import Iterable

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import CoverageItem, CoverageStatus, InsightCategory
from src.models.finding import AggregatedFinding, Aggregation, Finding, FindingConflict
from src.repositories.aggregation_repository import AggregationRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.finding_repository import FindingRepository
from src.services.extraction_service import extract_document_facts


class AggregationService:
    """Builds and stores product-level aggregations."""

    def __init__(
        self,
        document_repo: DocumentRepository,
        finding_repo: FindingRepository,
        aggregation_repo: AggregationRepository,
    ) -> None:
        self._document_repo = document_repo
        self._finding_repo = finding_repo
        self._aggregation_repo = aggregation_repo
        self._logger = get_logger(__name__)

    @staticmethod
    def _normalize_value(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip().lower()

    def _findings_from_text_items(
        self,
        *,
        product_id: str,
        document_id: str,
        version_id: str | None,
        category: InsightCategory,
        items: Iterable,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            value = getattr(item, "value", None) or ""
            if not value.strip():
                continue
            evidence = getattr(item, "evidence", None) or []
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    version_id=version_id,
                    category=category,
                    value=value.strip(),
                    normalized_value=self._normalize_value(value),
                    evidence=evidence,
                )
            )
        return findings

    def _findings_from_data_purpose_links(
        self,
        *,
        product_id: str,
        document_id: str,
        version_id: str | None,
        items: Iterable,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            data_type = getattr(item, "data_type", None) or ""
            if not data_type.strip():
                continue
            evidence = getattr(item, "evidence", None) or []
            attributes = {"purposes": getattr(item, "purposes", None) or []}
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    version_id=version_id,
                    category="data_collection",
                    value=data_type.strip(),
                    normalized_value=self._normalize_value(data_type),
                    attributes=attributes,
                    evidence=evidence,
                )
            )
        return findings

    def _findings_from_third_parties(
        self,
        *,
        product_id: str,
        document_id: str,
        version_id: str | None,
        items: Iterable,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            recipient = getattr(item, "recipient", None) or ""
            if not recipient.strip():
                continue
            evidence = getattr(item, "evidence", None) or []
            attributes = {
                "data_shared": getattr(item, "data_shared", None) or [],
                "purpose": getattr(item, "purpose", None),
                "risk_level": getattr(item, "risk_level", None),
            }
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    version_id=version_id,
                    category="data_sharing",
                    value=recipient.strip(),
                    normalized_value=self._normalize_value(recipient),
                    attributes=attributes,
                    evidence=evidence,
                )
            )
        return findings

    def _findings_from_contract_clauses(
        self,
        *,
        product_id: str,
        document_id: str,
        version_id: str | None,
        clauses: Iterable,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for clause in clauses:
            clause_type = getattr(clause, "clause_type", None)
            value = getattr(clause, "value", None)
            evidence = getattr(clause, "evidence", None) or []
            if not clause_type or not value:
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    version_id=version_id,
                    category=clause_type,
                    value=value,
                    normalized_value=self._normalize_value(value),
                    evidence=evidence,
                )
            )
        return findings

    def _findings_from_privacy_signals(
        self,
        *,
        product_id: str,
        document_id: str,
        version_id: str | None,
        privacy_signals,
    ) -> list[Finding]:
        findings: list[Finding] = []
        if not privacy_signals:
            return findings
        if privacy_signals.sells_data in {"yes", "no"}:
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    version_id=version_id,
                    category="data_sale",
                    value=f"sells_data: {privacy_signals.sells_data}",
                    normalized_value=f"sells_data:{privacy_signals.sells_data}",
                )
            )
        if privacy_signals.cross_site_tracking in {"yes", "no"}:
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    version_id=version_id,
                    category="cookies_tracking",
                    value=f"cross_site_tracking: {privacy_signals.cross_site_tracking}",
                    normalized_value=f"cross_site_tracking:{privacy_signals.cross_site_tracking}",
                )
            )
        return findings

    async def rebuild_findings_for_product(
        self, db: AgnosticDatabase, product_id: str
    ) -> list[Finding]:
        documents = await self._document_repo.find_by_product_id(db, product_id)
        all_findings: list[Finding] = []

        for doc in documents:
            extraction = await extract_document_facts(doc, use_cache=True)
            doc.extraction = extraction
            await self._document_repo.update(db, doc)

            # Remove old findings and rebuild
            await self._finding_repo.delete_findings_for_document(db, doc.id)

            findings = []
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="data_collection",
                items=extraction.data_collected,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="data_purposes",
                items=extraction.data_purposes,
            )
            findings += self._findings_from_data_purpose_links(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                items=extraction.data_collection_details,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="user_rights",
                items=extraction.your_rights,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="dangers",
                items=extraction.dangers,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="benefits",
                items=extraction.benefits,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="recommended_actions",
                items=extraction.recommended_actions,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="retention",
                items=extraction.retention_policy,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="security",
                items=extraction.security_measures,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="advertising",
                items=extraction.advertising_practices,
            )
            findings += self._findings_from_text_items(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                category="profiling_ai",
                items=extraction.profiling_ai,
            )
            findings += self._findings_from_third_parties(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                items=extraction.third_party_details,
            )
            findings += self._findings_from_contract_clauses(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                clauses=extraction.contract_clauses,
            )
            findings += self._findings_from_privacy_signals(
                product_id=doc.product_id,
                document_id=doc.id,
                version_id=None,
                privacy_signals=extraction.privacy_signals,
            )

            await self._finding_repo.create_many(db, findings)
            all_findings.extend(findings)

        return all_findings

    def _aggregate_findings(self, findings: list[Finding]) -> list[AggregatedFinding]:
        grouped: dict[tuple[str, str], AggregatedFinding] = {}
        for finding in findings:
            key = (
                finding.category,
                finding.normalized_value or self._normalize_value(finding.value),
            )
            if key not in grouped:
                grouped[key] = AggregatedFinding(
                    category=finding.category,
                    value=finding.value,
                    documents=[finding.document_id],
                    evidence=finding.evidence,
                    attributes=[finding.attributes] if finding.attributes else [],
                    confidence=finding.confidence,
                )
            else:
                grouped[key].documents.append(finding.document_id)
                if finding.evidence:
                    grouped[key].evidence.extend(finding.evidence)
                if finding.attributes:
                    grouped[key].attributes.append(finding.attributes)
        return list(grouped.values())

    def _detect_conflicts(self, findings: list[Finding]) -> list[FindingConflict]:
        conflicts: list[FindingConflict] = []
        by_category: dict[InsightCategory, set[str]] = {}
        for finding in findings:
            if finding.category not in {"data_sale", "advertising", "profiling_ai", "retention"}:
                continue
            by_category.setdefault(finding.category, set()).add(finding.normalized_value or "")

        for category, values in by_category.items():
            if len(values) > 1:
                conflicts.append(
                    FindingConflict(
                        category=category, description=f"Conflicting statements for {category}"
                    )
                )
        return conflicts

    def _build_coverage(self, findings: list[Finding], analyzed_docs: int) -> list[CoverageItem]:
        required_categories: list[InsightCategory] = [
            "data_collection",
            "data_purposes",
            "data_sharing",
            "user_rights",
            "retention",
            "security",
            "advertising",
            "profiling_ai",
            "data_sale",
            "liability",
            "arbitration",
            "governing_law",
            "jurisdiction",
        ]
        category_set = {f.category for f in findings}
        items: list[CoverageItem] = []
        for category in required_categories:
            status: CoverageStatus
            if analyzed_docs == 0:
                status = "not_analyzed"
            elif category in category_set:
                status = "found"
            else:
                status = "missing"
            items.append(CoverageItem(category=category, status=status))
        return items

    async def build_product_aggregation(
        self, db: AgnosticDatabase, product_id: str, product_slug: str
    ) -> Aggregation:
        findings = await self._finding_repo.find_by_product(db, product_id)
        documents = await self._document_repo.find_by_product_id(db, product_id)
        analyzed_docs = sum(1 for doc in documents if doc.extraction)
        aggregated_findings = self._aggregate_findings(findings)
        coverage = self._build_coverage(findings, analyzed_docs=analyzed_docs)
        conflicts = self._detect_conflicts(findings)

        aggregation = Aggregation(
            product_id=product_id,
            product_slug=product_slug,
            findings=aggregated_findings,
            conflicts=conflicts,
            coverage=coverage,
        )
        await self._aggregation_repo.save(db, aggregation)
        if coverage:
            status_counts: dict[str, int] = {}
            for item in coverage:
                status_counts[item.status] = status_counts.get(item.status, 0) + 1
            self._logger.info(
                "Aggregation coverage summary",
                product_slug=product_slug,
                total_categories=len(coverage),
                status_counts=status_counts,
            )
        return aggregation
