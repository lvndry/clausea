"""Aggregation service for merging findings across documents (v4)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from motor.core import AgnosticDatabase

from src.core.logging import get_logger
from src.models.document import (
    CoverageItem,
    CoverageStatus,
    DocumentExtraction,
    InsightCategory,
)
from src.models.finding import AggregatedFinding, Aggregation, Finding, FindingConflict
from src.repositories.aggregation_repository import AggregationRepository
from src.repositories.document_repository import DocumentRepository
from src.repositories.finding_repository import FindingRepository
from src.services.extraction_service import extract_document_facts


class AggregationService:
    """Builds and stores product-level aggregations from v4 extractions."""

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

    # ------------------------------------------------------------------
    # Generic finding builders
    # ------------------------------------------------------------------

    def _findings_from_text_items(
        self,
        *,
        product_id: str,
        document_id: str,
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
                    category=category,
                    value=value.strip(),
                    normalized_value=self._normalize_value(value),
                    evidence=evidence,
                )
            )
        return findings

    # ------------------------------------------------------------------
    # v4 specialised finding builders
    # ------------------------------------------------------------------

    def _findings_from_data_items(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            dt = getattr(item, "data_type", None) or ""
            if not dt.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="data_collection",
                    value=dt.strip(),
                    normalized_value=self._normalize_value(dt),
                    attributes={
                        "sensitivity": getattr(item, "sensitivity", "medium"),
                        "required": getattr(item, "required", "unclear"),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_purpose_links(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            dt = getattr(item, "data_type", None) or ""
            if not dt.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="data_purposes",
                    value=dt.strip(),
                    normalized_value=self._normalize_value(dt),
                    attributes={"purposes": getattr(item, "purposes", None) or []},
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_third_parties(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            recipient = getattr(item, "recipient", None) or ""
            if not recipient.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="data_sharing",
                    value=recipient.strip(),
                    normalized_value=self._normalize_value(recipient),
                    attributes={
                        "data_shared": getattr(item, "data_shared", None) or [],
                        "purpose": getattr(item, "purpose", None),
                        "risk_level": getattr(item, "risk_level", None),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_international_transfers(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            dest = getattr(item, "destination", None) or ""
            if not dest.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="international_transfers",
                    value=dest.strip(),
                    normalized_value=self._normalize_value(dest),
                    attributes={
                        "mechanism": getattr(item, "mechanism", None),
                        "data_types": getattr(item, "data_types", None) or [],
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_government_access(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            authority = getattr(item, "authority_type", None) or ""
            conditions = getattr(item, "conditions", None) or ""
            if not authority.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="government_access",
                    value=f"{authority.strip()}: {conditions.strip()}",
                    normalized_value=self._normalize_value(f"{authority}:{conditions}"),
                    attributes={"data_scope": getattr(item, "data_scope", None)},
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_corporate_family(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            entities = getattr(item, "entities", None) or []
            if not entities:
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="corporate_family_sharing",
                    value=", ".join(entities),
                    normalized_value=self._normalize_value(",".join(entities)),
                    attributes={
                        "data_shared": getattr(item, "data_shared", None) or [],
                        "purpose": getattr(item, "purpose", None),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_user_rights(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            rt = getattr(item, "right_type", None) or ""
            if not rt.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="user_rights",
                    value=rt.strip(),
                    normalized_value=self._normalize_value(rt),
                    attributes={
                        "description": getattr(item, "description", None),
                        "mechanism": getattr(item, "mechanism", None),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_ai_usage(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            ut = getattr(item, "usage_type", None) or ""
            desc = getattr(item, "description", None) or ""
            if not ut.strip():
                continue
            category: InsightCategory = (
                "ai_training" if ut == "training_on_user_data" else "automated_decisions"
            )
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category=category,
                    value=desc.strip() or ut.strip(),
                    normalized_value=self._normalize_value(f"{ut}:{desc}"),
                    attributes={
                        "usage_type": ut,
                        "data_involved": getattr(item, "data_involved", None) or [],
                        "opt_out_available": getattr(item, "opt_out_available", "unclear"),
                        "opt_out_mechanism": getattr(item, "opt_out_mechanism", None),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_liability(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            desc = getattr(item, "description", None) or ""
            if not desc.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="liability",
                    value=desc.strip(),
                    normalized_value=self._normalize_value(desc),
                    attributes={
                        "scope": getattr(item, "scope", None),
                        "limitation_type": getattr(item, "limitation_type", None),
                        "extends_beyond_product": getattr(item, "extends_beyond_product", False),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_dispute_resolution(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            mech = getattr(item, "mechanism", None) or ""
            desc = getattr(item, "description", None) or mech
            if not mech.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="dispute_resolution",
                    value=desc.strip() if desc else mech.strip(),
                    normalized_value=self._normalize_value(mech),
                    attributes={
                        "mechanism": mech,
                        "class_action_waiver": getattr(item, "class_action_waiver", False),
                        "jury_trial_waiver": getattr(item, "jury_trial_waiver", False),
                        "venue": getattr(item, "venue", None),
                        "governing_law": getattr(item, "governing_law", None),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_content_ownership(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            desc = getattr(item, "description", None) or ""
            if not desc.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="content_ownership",
                    value=desc.strip(),
                    normalized_value=self._normalize_value(desc),
                    attributes={
                        "ownership_type": getattr(item, "ownership_type", None),
                        "scope": getattr(item, "scope", None),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_retention_rules(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            scope = getattr(item, "data_scope", None) or ""
            if not scope.strip():
                continue
            duration = getattr(item, "duration", None) or ""
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="retention",
                    value=f"{scope.strip()}: {duration.strip()}"
                    if duration.strip()
                    else scope.strip(),
                    normalized_value=self._normalize_value(scope),
                    attributes={
                        "duration": duration.strip() if duration else None,
                        "conditions": getattr(item, "conditions", None),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_cookie_trackers(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            name = getattr(item, "name_or_type", None) or ""
            if not name.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="cookies_tracking",
                    value=name.strip(),
                    normalized_value=self._normalize_value(name),
                    attributes={
                        "category": getattr(item, "category", "other"),
                        "third_party": getattr(item, "third_party", False),
                        "opt_out_mechanism": getattr(item, "opt_out_mechanism", None),
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_children_policy(
        self, *, product_id: str, document_id: str, children_policy
    ) -> list[Finding]:
        if not children_policy:
            return []
        min_age = getattr(children_policy, "minimum_age", None)
        parental = getattr(children_policy, "parental_consent_required", False)
        protections = getattr(children_policy, "special_protections", None)
        if min_age is None and not parental and not protections:
            return []
        parts: list[str] = []
        if min_age is not None:
            parts.append(f"Minimum age: {min_age}")
        if parental:
            parts.append("Parental consent required")
        if protections:
            parts.append(protections)
        value = "; ".join(parts)
        return [
            Finding(
                product_id=product_id,
                document_id=document_id,
                category="children",
                value=value,
                normalized_value=self._normalize_value(value),
                attributes={
                    "minimum_age": min_age,
                    "parental_consent_required": parental,
                    "special_protections": protections,
                },
                evidence=getattr(children_policy, "evidence", None) or [],
            )
        ]

    def _findings_from_scope_expansion(
        self, *, product_id: str, document_id: str, items: Iterable
    ) -> list[Finding]:
        findings: list[Finding] = []
        for item in items:
            desc = getattr(item, "description", None) or ""
            if not desc.strip():
                continue
            findings.append(
                Finding(
                    product_id=product_id,
                    document_id=document_id,
                    category="scope_expansion",
                    value=desc.strip(),
                    normalized_value=self._normalize_value(desc),
                    attributes={
                        "scope_type": getattr(item, "scope_type", None),
                        "entities_affected": getattr(item, "entities_affected", None) or [],
                    },
                    evidence=getattr(item, "evidence", None) or [],
                )
            )
        return findings

    def _findings_from_privacy_signals(
        self, *, product_id: str, document_id: str, privacy_signals
    ) -> list[Finding]:
        findings: list[Finding] = []
        if not privacy_signals:
            return findings

        signal_to_category: list[tuple[str, str, InsightCategory]] = [
            ("sells_data", "yes", "data_sale"),
            ("sells_data", "no", "data_sale"),
            ("cross_site_tracking", "yes", "cookies_tracking"),
            ("cross_site_tracking", "no", "cookies_tracking"),
            ("ai_training_on_user_data", "yes", "ai_training"),
            ("ai_training_on_user_data", "no", "ai_training"),
            ("breach_notification", "yes", "breach_notification"),
            ("breach_notification", "no", "breach_notification"),
            ("children_data_collection", "yes", "children"),
            ("children_data_collection", "no", "children"),
        ]
        for attr, trigger_val, category in signal_to_category:
            val = getattr(privacy_signals, attr, None)
            if val == trigger_val:
                findings.append(
                    Finding(
                        product_id=product_id,
                        document_id=document_id,
                        category=category,
                        value=f"{attr}: {val}",
                        normalized_value=f"{attr}:{val}",
                    )
                )
        return findings

    # ------------------------------------------------------------------
    # Build findings from a v4 extraction
    # ------------------------------------------------------------------

    def _extraction_to_findings(
        self, *, product_id: str, document_id: str, extraction: DocumentExtraction
    ) -> list[Finding]:
        f: list[Finding] = []

        # Cluster 1
        f += self._findings_from_data_items(
            product_id=product_id, document_id=document_id, items=extraction.data_collected
        )
        f += self._findings_from_purpose_links(
            product_id=product_id, document_id=document_id, items=extraction.data_purposes
        )
        f += self._findings_from_retention_rules(
            product_id=product_id, document_id=document_id, items=extraction.retention_policies
        )
        f += self._findings_from_text_items(
            product_id=product_id,
            document_id=document_id,
            category="security",
            items=extraction.security_measures,
        )
        f += self._findings_from_cookie_trackers(
            product_id=product_id, document_id=document_id, items=extraction.cookies_and_trackers
        )

        # Cluster 2
        f += self._findings_from_third_parties(
            product_id=product_id, document_id=document_id, items=extraction.third_party_details
        )
        f += self._findings_from_international_transfers(
            product_id=product_id, document_id=document_id, items=extraction.international_transfers
        )
        f += self._findings_from_government_access(
            product_id=product_id, document_id=document_id, items=extraction.government_access
        )
        f += self._findings_from_corporate_family(
            product_id=product_id,
            document_id=document_id,
            items=extraction.corporate_family_sharing,
        )

        # Cluster 3
        f += self._findings_from_user_rights(
            product_id=product_id, document_id=document_id, items=extraction.user_rights
        )
        f += self._findings_from_text_items(
            product_id=product_id,
            document_id=document_id,
            category="consent_mechanisms",
            items=extraction.consent_mechanisms,
        )
        f += self._findings_from_text_items(
            product_id=product_id,
            document_id=document_id,
            category="account_lifecycle",
            items=extraction.account_lifecycle,
        )
        f += self._findings_from_ai_usage(
            product_id=product_id, document_id=document_id, items=extraction.ai_usage
        )
        f += self._findings_from_children_policy(
            product_id=product_id,
            document_id=document_id,
            children_policy=extraction.children_policy,
        )

        # Cluster 4
        f += self._findings_from_liability(
            product_id=product_id, document_id=document_id, items=extraction.liability
        )
        f += self._findings_from_dispute_resolution(
            product_id=product_id, document_id=document_id, items=extraction.dispute_resolution
        )
        f += self._findings_from_content_ownership(
            product_id=product_id, document_id=document_id, items=extraction.content_ownership
        )
        f += self._findings_from_scope_expansion(
            product_id=product_id, document_id=document_id, items=extraction.scope_expansion
        )
        f += self._findings_from_text_items(
            product_id=product_id,
            document_id=document_id,
            category="indemnification",
            items=extraction.indemnification,
        )
        f += self._findings_from_text_items(
            product_id=product_id,
            document_id=document_id,
            category="termination_consequences",
            items=extraction.termination_consequences,
        )

        # Cross-cutting
        f += self._findings_from_text_items(
            product_id=product_id,
            document_id=document_id,
            category="dangers",
            items=extraction.dangers,
        )
        f += self._findings_from_text_items(
            product_id=product_id,
            document_id=document_id,
            category="benefits",
            items=extraction.benefits,
        )
        f += self._findings_from_text_items(
            product_id=product_id,
            document_id=document_id,
            category="recommended_actions",
            items=extraction.recommended_actions,
        )
        f += self._findings_from_privacy_signals(
            product_id=product_id,
            document_id=document_id,
            privacy_signals=extraction.privacy_signals,
        )

        return f

    # ------------------------------------------------------------------
    # Top-level operations
    # ------------------------------------------------------------------

    async def rebuild_findings_for_product(
        self, db: AgnosticDatabase, product_id: str
    ) -> list[Finding]:
        documents = await self._document_repo.find_by_product_id(db, product_id)
        all_findings: list[Finding] = []

        for doc in documents:
            extraction = await extract_document_facts(doc, use_cache=True)
            doc.extraction = extraction
            await self._document_repo.update(db, doc)

            await self._finding_repo.delete_findings_for_document(db, doc.id)
            findings = self._extraction_to_findings(
                product_id=doc.product_id, document_id=doc.id, extraction=extraction
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
        conflictable: set[str] = {
            "data_sale",
            "retention",
            "ai_training",
            "breach_notification",
            "children",
        }
        by_category: dict[InsightCategory, set[str]] = {}
        for finding in findings:
            if finding.category not in conflictable:
                continue
            by_category.setdefault(finding.category, set()).add(finding.normalized_value or "")

        for category, values in by_category.items():
            if len(values) > 1:
                conflicts.append(
                    FindingConflict(
                        category=category,
                        description=f"Conflicting statements for {category}",
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
            "cookies_tracking",
            "data_sale",
            "international_transfers",
            "government_access",
            "corporate_family_sharing",
            "ai_training",
            "automated_decisions",
            "content_ownership",
            "scope_expansion",
            "liability",
            "dispute_resolution",
            "indemnification",
            "termination_consequences",
            "children",
            "breach_notification",
            "consent_mechanisms",
            "account_lifecycle",
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
