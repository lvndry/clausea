import json
from datetime import datetime
from typing import Any, Literal

import shortuuid
from pydantic import BaseModel, Field, field_validator

TierRelevance = Literal["core", "extended"]

CORE_DOC_TYPES = {
    "privacy_policy",
    "terms_of_service",
    "cookie_policy",
    "gdpr_policy",
    "terms_of_use",
    "terms_and_conditions",
}


class DocumentAnalysisScores(BaseModel):
    score: int
    justification: str


class EvidenceSpan(BaseModel):
    """A concrete piece of evidence anchored into a specific document text."""

    document_id: str
    url: str
    content_hash: str | None = None
    quote: str
    start_char: int | None = None
    end_char: int | None = None
    section_title: str | None = None
    verified: bool = True


class ExtractedTextItem(BaseModel):
    """An extracted, normalized text item with evidence."""

    value: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedDataPurposeLink(BaseModel):
    """Evidence-backed DataPurposeLink."""

    data_type: str
    purposes: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedThirdPartyRecipient(BaseModel):
    """Evidence-backed ThirdPartyRecipient."""

    recipient: str
    data_shared: list[str] = Field(default_factory=list)
    purpose: str | None = None
    risk_level: Literal["low", "medium", "high"] = "medium"
    evidence: list[EvidenceSpan] = Field(default_factory=list)


ContractClauseType = Literal["liability", "arbitration", "governing_law", "jurisdiction"]


class ExtractedContractClause(BaseModel):
    """Evidence-backed contract clause (v3 legacy, kept for aggregation compat)."""

    clause_type: ContractClauseType
    value: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# v4 extraction models — richer, purpose-built types
# ---------------------------------------------------------------------------


class ExtractedDataItem(BaseModel):
    """A specific data type collected, with sensitivity and optionality."""

    data_type: str
    sensitivity: Literal["low", "medium", "high", "sensitive"] = "medium"
    required: Literal["required", "optional", "unclear"] = "unclear"
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedRetentionRule(BaseModel):
    """Retention policy linked to a data scope."""

    data_scope: str
    duration: str
    conditions: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedCookieTracker(BaseModel):
    """A cookie or tracking technology with its properties."""

    name_or_type: str
    category: Literal["essential", "analytics", "advertising", "social", "other"] = "other"
    duration: str | None = None
    third_party: bool = False
    opt_out_mechanism: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedInternationalTransfer(BaseModel):
    """Cross-border data transfer with legal mechanism."""

    destination: str
    mechanism: str | None = None
    data_types: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedGovernmentAccess(BaseModel):
    """Conditions under which data is shared with government or law enforcement."""

    authority_type: str
    conditions: str
    data_scope: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedCorporateFamilySharing(BaseModel):
    """Data sharing within a corporate group or set of affiliated entities."""

    entities: list[str] = Field(default_factory=list)
    data_shared: list[str] = Field(default_factory=list)
    purpose: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedUserRight(BaseModel):
    """A user right with the mechanism to exercise it."""

    right_type: str
    description: str
    mechanism: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedAIUsage(BaseModel):
    """How AI, ML, or automated decision-making is applied to user data."""

    usage_type: Literal[
        "training_on_user_data",
        "automated_decisions",
        "profiling",
        "content_generation",
        "recommendation",
        "moderation",
        "other",
    ]
    description: str
    data_involved: list[str] = Field(default_factory=list)
    opt_out_available: Literal["yes", "no", "unclear"] = "unclear"
    opt_out_mechanism: str | None = None
    consequences: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedChildrenPolicy(BaseModel):
    """Policies specifically about children and minors."""

    minimum_age: int | None = None
    parental_consent_required: bool = False
    special_protections: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedLiability(BaseModel):
    """Liability limitation, waiver, or indemnification clause."""

    scope: str
    limitation_type: Literal["cap", "waiver", "exclusion", "indemnification"]
    description: str
    extends_beyond_product: bool = False
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedDisputeResolution(BaseModel):
    """Dispute resolution mechanism and associated waivers."""

    mechanism: Literal["arbitration", "litigation", "mediation", "other"]
    class_action_waiver: bool = False
    jury_trial_waiver: bool = False
    venue: str | None = None
    governing_law: str | None = None
    description: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedContentOwnership(BaseModel):
    """Rights the company claims over user-generated content or likeness."""

    ownership_type: Literal[
        "license_to_company",
        "user_retains",
        "company_owns",
        "ai_training_rights",
        "likeness_rights",
        "other",
    ]
    scope: str
    description: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedScopeExpansion(BaseModel):
    """Clauses that extend the reach of the agreement beyond what users expect."""

    scope_type: Literal[
        "cross_entity",
        "survival_clause",
        "unilateral_modification",
        "binding_heirs",
        "physical_world",
        "other",
    ]
    description: str
    entities_affected: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Privacy signals (v4 — expanded with AI, breach, minimization, children)
# ---------------------------------------------------------------------------


class PrivacySignals(BaseModel):
    """Quick-scan indicators answering the most common user questions."""

    sells_data: Literal["yes", "no", "unclear"] = "unclear"
    cross_site_tracking: Literal["yes", "no", "unclear"] = "unclear"
    account_deletion: Literal["self_service", "request_required", "not_specified"] = "not_specified"
    data_retention_summary: str | None = None
    consent_model: Literal["opt_in", "opt_out", "mixed", "not_specified"] = "not_specified"
    ai_training_on_user_data: Literal["yes", "no", "unclear"] = "unclear"
    breach_notification: Literal["yes", "no", "not_specified"] = "not_specified"
    data_minimization: Literal["yes", "no", "unclear"] = "unclear"
    children_data_collection: Literal["yes", "no", "not_specified"] = "not_specified"
    evidence: list[EvidenceSpan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Document extraction (v4)
# ---------------------------------------------------------------------------


class DocumentExtraction(BaseModel):
    """Evidence-backed structured facts for a single document (v4).

    Organised into four extraction clusters:
      1. Data Practices — collection, purposes, retention, security, cookies
      2. Sharing & Transfers — third parties, international, government, corporate family
      3. Rights & AI — user rights, consent, account lifecycle, AI/profiling, children
      4. Legal Terms & Scope — liability, disputes, content ownership, scope expansion
    """

    version: str = "v4"
    generated_at: datetime = Field(default_factory=datetime.now)
    source_content_hash: str

    # Cluster 1: Data Practices
    data_collected: list[ExtractedDataItem] = Field(default_factory=list)
    data_purposes: list[ExtractedDataPurposeLink] = Field(default_factory=list)
    retention_policies: list[ExtractedRetentionRule] = Field(default_factory=list)
    security_measures: list[ExtractedTextItem] = Field(default_factory=list)
    cookies_and_trackers: list[ExtractedCookieTracker] = Field(default_factory=list)

    # Cluster 2: Sharing & Transfers
    third_party_details: list[ExtractedThirdPartyRecipient] = Field(default_factory=list)
    international_transfers: list[ExtractedInternationalTransfer] = Field(default_factory=list)
    government_access: list[ExtractedGovernmentAccess] = Field(default_factory=list)
    corporate_family_sharing: list[ExtractedCorporateFamilySharing] = Field(default_factory=list)

    # Cluster 3: Rights & AI
    user_rights: list[ExtractedUserRight] = Field(default_factory=list)
    consent_mechanisms: list[ExtractedTextItem] = Field(default_factory=list)
    account_lifecycle: list[ExtractedTextItem] = Field(default_factory=list)
    ai_usage: list[ExtractedAIUsage] = Field(default_factory=list)
    children_policy: ExtractedChildrenPolicy | None = None

    # Cluster 4: Legal Terms & Scope
    liability: list[ExtractedLiability] = Field(default_factory=list)
    dispute_resolution: list[ExtractedDisputeResolution] = Field(default_factory=list)
    content_ownership: list[ExtractedContentOwnership] = Field(default_factory=list)
    scope_expansion: list[ExtractedScopeExpansion] = Field(default_factory=list)
    indemnification: list[ExtractedTextItem] = Field(default_factory=list)
    termination_consequences: list[ExtractedTextItem] = Field(default_factory=list)

    # Synthesised signals
    privacy_signals: PrivacySignals | None = None

    # Cross-cutting assessments (populated by all clusters)
    dangers: list[ExtractedTextItem] = Field(default_factory=list)
    benefits: list[ExtractedTextItem] = Field(default_factory=list)
    recommended_actions: list[ExtractedTextItem] = Field(default_factory=list)


class KeypointWithEvidence(BaseModel):
    """A user-facing keypoint paired with evidence spans."""

    keypoint: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


InsightCategory = Literal[
    "data_collection",
    "data_purposes",
    "data_sharing",
    "user_rights",
    "retention",
    "deletion",
    "security",
    "advertising",
    "profiling_ai",
    "data_sale",
    "cookies_tracking",
    "children",
    "dangers",
    "benefits",
    "recommended_actions",
    "liability",
    "arbitration",
    "governing_law",
    "jurisdiction",
    # v4 additions
    "international_transfers",
    "government_access",
    "corporate_family_sharing",
    "ai_training",
    "automated_decisions",
    "content_ownership",
    "scope_expansion",
    "indemnification",
    "termination_consequences",
    "consent_mechanisms",
    "account_lifecycle",
    "breach_notification",
    "dispute_resolution",
]


CoverageStatus = Literal["found", "missing", "ambiguous", "not_analyzed"]


class CoverageItem(BaseModel):
    """Coverage status for a required insight category."""

    category: InsightCategory
    status: CoverageStatus
    notes: str | None = None
    evidence_count: int | None = None


class DocumentAnalysis(BaseModel):
    """
    Document analysis model.

    - summary: A user-oriented explanation of what this document means in practice.
    - scores: A dictionary with the following required keys (each value is a DocumentAnalysisScores object with score and justification):
        - transparency: A number between 0 and 10 indicating the transparency of the document.
        - data_collection_scope: A number between 0 and 10 indicating the scope of data collection.
        - user_control: A number between 0 and 10 indicating how much control users have over their data.
        - third_party_sharing: A number between 0 and 10 indicating third-party sharing practices.
        - data_retention_score: A DocumentAnalysisScores object indicating data retention practices.
        - security_score: A DocumentAnalysisScores object indicating security practices.
    - risk_score: Overall risk score from 0-10 (calculated from component scores).
    - verdict: Privacy friendliness level ("very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive").
    - liability_risk: (Optional) Risk of liability exposure from contract terms (0-10, for business users).
    - compliance_status: (Optional) Compliance scores per regulation (e.g., {"GDPR": 8, "CCPA": 7}).
    - keypoints: A list of bullet points capturing the most relevant and impactful ideas.
    - scope: (Optional) The scope of the document - whether it applies globally, to specific products, regions, or services.
    """

    summary: str
    scores: dict[str, DocumentAnalysisScores]
    risk_score: int = Field(default=5, ge=0, le=10, description="Overall risk score from 0-10")
    verdict: Literal[
        "very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"
    ] = Field(default="moderate", description="Privacy friendliness level based on risk score")
    liability_risk: int | None = Field(
        default=None, ge=0, le=10, description="Liability risk score (0-10, for business users)"
    )
    compliance_status: dict[str, int] | None = Field(
        default=None, description="Compliance scores per regulation (e.g., {'GDPR': 8, 'CCPA': 7})"
    )
    keypoints: list[str] | None = None
    # Optional, evidence-backed keypoints (additive / backward compatible).
    keypoints_with_evidence: list[KeypointWithEvidence] | None = None
    scope: str | None = Field(
        default=None,
        description="Document scope - e.g., 'Global privacy policy', 'Terms for Product X', 'EU-specific policy'",
    )
    privacy_signals: PrivacySignals | None = None
    coverage: list[CoverageItem] | None = None
    contract_clauses: list[str] | None = None

    @field_validator("summary", mode="before")
    @classmethod
    def clean_summary(cls, v: str | None) -> str:
        """Clean summary string, handling potential JSON-encoded responses."""
        if v is None:
            return ""
        result = v.strip()

        # Try to parse as JSON and extract summary field if present
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and "summary" in parsed:
                return str(parsed["summary"])
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON or not a dict, continue with original string
            pass

        return str(result)  # Ensure we return str, not Any

    @field_validator("compliance_status", mode="before")
    @classmethod
    def clean_compliance_status(cls, v: dict[str, Any] | None) -> dict[str, int] | None:
        if not v or not isinstance(v, dict):
            return None
        cleaned = {}
        for k, val in v.items():
            if val is not None:
                try:
                    cleaned[str(k)] = int(val)
                except (ValueError, TypeError):
                    pass
        return cleaned if cleaned else None


class MetaSummaryScore(BaseModel):
    score: int
    justification: str


class MetaSummaryScores(BaseModel):
    transparency: MetaSummaryScore
    data_collection_scope: MetaSummaryScore
    user_control: MetaSummaryScore
    third_party_sharing: MetaSummaryScore


class DataPurposeLink(BaseModel):
    """Links a specific data type to its collection purposes."""

    data_type: str  # e.g., "Email address"
    purposes: list[str]  # e.g., ["Account creation", "Marketing emails"]


class ThirdPartyRecipient(BaseModel):
    """Details about a third party that receives user data."""

    recipient: str  # e.g., "Advertisers", "Analytics providers"
    data_shared: list[str]  # e.g., ["email", "browsing history"]
    purpose: str | None = None  # e.g., "Targeted advertising"
    risk_level: Literal["low", "medium", "high"] = "medium"


class MetaSummary(BaseModel):
    summary: str
    scores: MetaSummaryScores
    risk_score: int
    verdict: Literal[
        "very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"
    ]
    keypoints: list[str]
    data_collected: list[str] | None = (
        None  # 10-20 specific data types: ["Email address", "IP address", "Location data (GPS)", ...]
    )
    data_purposes: list[str] | None = (
        None  # 8-15 purposes: ["Core service delivery", "Personalized advertising", ...]
    )
    # New structured fields for Overview redesign
    data_collection_details: list[DataPurposeLink] | None = (
        None  # Structured: each data type linked to its purposes
    )
    third_party_details: list[ThirdPartyRecipient] | None = (
        None  # Structured: who gets data, what, and why
    )
    your_rights: list[str] | None = (
        None  # 8-12 rights with explicit instructions: ["Access your data (email, profile) via account.organization.com/privacy", ...]
    )
    dangers: list[str] | None = None  # 5-7 specific concerns with details
    benefits: list[str] | None = None  # 5-7 specific positive privacy protections
    recommended_actions: list[str] | None = None  # 5-8 actionable steps with specific instructions
    privacy_signals: PrivacySignals | None = None
    compliance_status: dict[str, int] | None = None  # {"GDPR": 8, "CCPA": 7}
    coverage: list[CoverageItem] | None = None
    contract_clauses: list[str] | None = None

    @field_validator("compliance_status", mode="before")
    @classmethod
    def clean_compliance_status(cls, v: dict[str, Any] | None) -> dict[str, int] | None:
        if not v or not isinstance(v, dict):
            return None
        cleaned = {}
        for k, val in v.items():
            if val is not None:
                try:
                    cleaned[str(k)] = int(val)
                except (ValueError, TypeError):
                    pass
        return cleaned if cleaned else None


DocType = Literal[
    "privacy_policy",
    "terms_of_service",
    "cookie_policy",
    "terms_of_use",
    "terms_and_conditions",
    "data_processing_agreement",
    "community_guidelines",
    "children_privacy_policy",
    "gdpr_policy",
    "copyright_policy",
    "other",
    "unclassified",
]

Region = Literal[
    "global",
    "US",
    "EU",
    "EFTA",
    "UK",
    "Asia",
    "Australia",
    "Canada",
    "Brazil",
    "South Korea",
    "Israel",
    "Other",
]


class ComplianceBreakdown(BaseModel):
    """Detailed breakdown of compliance for a specific regulation."""

    score: int = Field(ge=0, le=10)
    status: Literal["Compliant", "Partially Compliant", "Non-Compliant", "Unknown"]
    strengths: list[str]  # What they do well
    gaps: list[str]  # What's missing or unclear


class ProductOverview(BaseModel):
    """
    Level 1: Quick decision-making overview.
    For users who need to decide "Should I use this service?" in under 60 seconds.
    """

    # Identity
    product_name: str
    product_slug: str
    company_name: str | None = None
    last_updated: datetime | None = None

    # Decision Support
    verdict: Literal[
        "very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"
    ]
    risk_score: int = Field(ge=0, le=10)
    one_line_summary: str  # "Spotify collects extensive data for ads but offers strong user rights"

    # Core Insights (what users most want to know)
    data_collected: list[str] | None = None  # ["Email", "Listening history", "Location"]
    data_purposes: list[str] | None = None  # ["Core service", "Advertising", "Analytics"]
    third_party_sharing: str | None = None  # "Shared with advertisers and analytics partners"

    # Structured data for Overview redesign
    data_collection_details: list[DataPurposeLink] | None = None  # Data type → purposes
    third_party_details: list[ThirdPartyRecipient] | None = None  # Recipients with specifics

    # Top keypoints and document metadata for quick UI
    keypoints: list[str] | None = None
    document_counts: dict[str, int] | None = None  # { total: n, analyzed: n, pending: n }
    document_types: dict[str, int] | None = None

    # Detailed scoring breakdown (surfaced from MetaSummaryScores)
    detailed_scores: MetaSummaryScores | None = None

    # Compliance status per regulation (e.g., {"GDPR": 8, "CCPA": 7})
    compliance_status: dict[str, int] | None = None

    # Quick-scan privacy signals
    privacy_signals: PrivacySignals | None = None

    # User Empowerment
    your_rights: list[str] | None = (
        None  # 8-12 rights with explicit instructions: ["Access your data (email, profile) via account.organization.com/privacy", ...]
    )
    dangers: list[str] | None = None  # 5-7 specific concerns with details
    benefits: list[str] | None = None  # 5-7 specific positive privacy protections

    # Actions
    recommended_actions: list[str] | None = None  # 5-8 actionable steps with specific instructions
    coverage: list[CoverageItem] | None = None
    contract_clauses: list[str] | None = None

    @field_validator("compliance_status", mode="before")
    @classmethod
    def clean_compliance_status(cls, v: dict[str, Any] | None) -> dict[str, int] | None:
        if not v or not isinstance(v, dict):
            return None
        cleaned = {}
        for k, val in v.items():
            if val is not None:
                try:
                    cleaned[str(k)] = int(val)
                except (ValueError, TypeError):
                    pass
        return cleaned if cleaned else None


class DocumentSummary(BaseModel):
    """Lightweight summary of a document for listing purposes."""

    id: str
    title: str | None
    doc_type: DocType
    url: str
    last_updated: datetime | None = None
    verdict: (
        Literal["very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"]
        | None
    ) = None
    risk_score: int | None = Field(default=None, ge=0, le=10)
    top_concerns: list[str] | None = None  # Top 3
    summary: str | None = None  # User-oriented explanation from analysis
    keypoints: list[str] | None = None  # Key bullet points from analysis
    keypoints_with_evidence: list[KeypointWithEvidence] | None = None  # Optional citations

    @classmethod
    def from_document(cls, doc: "Document") -> "DocumentSummary":
        """Factory method to create a DocumentSummary from a Document model."""
        # Only extract the fields that DocumentSummary needs from Document
        summary_data = doc.model_dump()

        summary_data["last_updated"] = doc.effective_date

        if doc.analysis:
            summary_data["summary"] = doc.analysis.summary
            summary_data["keypoints"] = doc.analysis.keypoints
            summary_data["keypoints_with_evidence"] = doc.analysis.keypoints_with_evidence
            summary_data["verdict"] = doc.analysis.verdict
            summary_data["risk_score"] = doc.analysis.risk_score
        else:
            summary_data["summary"] = None
            summary_data["keypoints"] = None
            summary_data["keypoints_with_evidence"] = None
            summary_data["verdict"] = None
            summary_data["risk_score"] = None

        return cls(**summary_data)


class ProductAnalysis(BaseModel):
    """
    Level 2: Full analysis with detailed scores and justifications.
    For users who need comprehensive understanding (2-5 minutes).
    """

    # Include Level 1
    overview: ProductOverview

    # Detailed scores from MetaSummary
    detailed_scores: MetaSummaryScores

    # Compliance breakdown (per regulation)
    compliance: dict[str, ComplianceBreakdown] | None = None  # {"GDPR": {...}, "CCPA": {...}}

    # Complete keypoints (not just top 5)
    all_keypoints: list[str]

    # Document metadata
    documents: list[DocumentSummary]


class CriticalClause(BaseModel):
    """Analysis of a critical clause in a document."""

    clause_type: Literal[
        "data_collection",
        "data_sharing",
        "user_rights",
        "liability",
        "indemnification",
        "retention",
        "deletion",
        "security",
        "breach_notification",
        "dispute_resolution",
        "governing_law",
    ]
    section_title: str | None = None  # "Section 3: Data Collection"
    quote: str  # Exact text from document
    risk_level: Literal["low", "medium", "high", "critical"]
    analysis: str  # Explanation of what this means
    compliance_impact: list[str] = Field(default_factory=list)  # Which regulations this affects


class DocumentSection(BaseModel):
    """Important section of a document with analysis."""

    section_title: str
    content: str  # Full text of section
    importance: Literal["low", "medium", "high", "critical"]
    analysis: str  # What this section means
    related_clauses: list[str] = Field(
        default_factory=list
    )  # IDs or indices of related critical clauses


class DocumentRiskBreakdown(BaseModel):
    """Detailed risk assessment for a document."""

    overall_risk: int = Field(ge=0, le=10)
    risk_by_category: dict[str, int] = Field(
        default_factory=dict
    )  # {"data_sharing": 8, "retention": 5}
    top_concerns: list[str] = Field(default_factory=list)  # Specific concerns
    positive_protections: list[str] = Field(default_factory=list)  # Good practices
    missing_information: list[str] = Field(default_factory=list)  # What's not mentioned
    scope: str | None = Field(
        default=None,
        description="Document scope - e.g., 'Global privacy policy', 'Terms for Product X', 'EU-specific policy'. Used to contextualize risk assessment.",
    )


class DocumentDeepAnalysis(BaseModel):
    """Deep analysis of a single document."""

    document_id: str
    document_type: DocType
    title: str | None = None
    url: str

    # Document metadata
    effective_date: datetime | None = None
    last_updated: datetime | None = None
    locale: str | None = None
    regions: list[Region] = Field(default_factory=list)

    # Full analysis from Level 2
    analysis: DocumentAnalysis

    # Deep analysis additions
    critical_clauses: list[CriticalClause] = Field(default_factory=list)
    document_risk_breakdown: DocumentRiskBreakdown
    key_sections: list[DocumentSection] = Field(
        default_factory=list
    )  # Important sections with quotes


class DocumentContradiction(BaseModel):
    """Identified contradiction between documents."""

    document_a: str  # Document ID or name
    document_b: str
    contradiction_type: str  # "data_sharing", "retention", etc.
    description: str  # What contradicts
    document_a_statement: str  # What document A says
    document_b_statement: str  # What document B says
    impact: str  # Risk/legal impact
    recommendation: str  # How to resolve


class DocumentRelationship(BaseModel):
    """Relationship between documents."""

    document_a: str
    document_b: str
    relationship_type: Literal["references", "supersedes", "complements", "conflicts"]
    description: str
    evidence: str  # Quote or reference supporting the relationship


class CrossDocumentAnalysis(BaseModel):
    """Analysis across all documents."""

    contradictions: list[DocumentContradiction] = Field(default_factory=list)
    information_gaps: list[str] = Field(default_factory=list)
    document_relationships: list[DocumentRelationship] = Field(default_factory=list)


class ComplianceViolation(BaseModel):
    """Specific compliance violation."""

    requirement: str  # "GDPR Article 15 - Right of access"
    violation_type: Literal["missing", "unclear", "non_compliant"]
    description: str  # What's wrong
    severity: Literal["low", "medium", "high", "critical"]
    remediation: str  # How to fix


class EnhancedComplianceBreakdown(BaseModel):
    """Enhanced compliance analysis per regulation."""

    regulation: str  # "GDPR", "CCPA", etc.
    score: int = Field(ge=0, le=10)
    status: Literal["Compliant", "Partially Compliant", "Non-Compliant", "Unknown"]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    violations: list[ComplianceViolation] = Field(default_factory=list)  # Specific violations
    remediation_recommendations: list[str] = Field(default_factory=list)
    detailed_analysis: str  # Comprehensive explanation


class PrioritizedAction(BaseModel):
    """Action item with priority."""

    action: str
    priority: Literal["critical", "high", "medium", "low"]
    rationale: str
    deadline: str | None = None  # "Immediate", "Within 30 days", etc.


class IndividualImpact(BaseModel):
    """Privacy impact for individual users."""

    privacy_risk_level: Literal["low", "medium", "high", "critical"]
    data_exposure_summary: str
    recommended_actions: list[PrioritizedAction] = Field(default_factory=list)


class BusinessImpact(BaseModel):
    """Business impact for enterprise users."""

    liability_exposure: int = Field(ge=0, le=10)
    contract_risk_score: int = Field(ge=0, le=10)
    vendor_risk_score: int = Field(ge=0, le=10)
    financial_impact: str  # Potential financial consequences
    reputational_risk: str  # Reputational implications
    operational_risk: str  # Operational implications
    recommended_actions: list[PrioritizedAction] = Field(default_factory=list)


class BusinessImpactAssessment(BaseModel):
    """Business impact assessment."""

    for_individuals: IndividualImpact
    for_businesses: BusinessImpact


class RiskPrioritization(BaseModel):
    """Prioritized list of risks."""

    critical: list[str] = Field(default_factory=list)
    high: list[str] = Field(default_factory=list)
    medium: list[str] = Field(default_factory=list)
    low: list[str] = Field(default_factory=list)


class ProductDeepAnalysis(BaseModel):
    """
    Level 3: Deep analysis for legal/compliance review.
    For users who need comprehensive, detailed analysis (10-20 minutes).
    """

    # Include Level 2
    analysis: ProductAnalysis

    # Document-by-document deep breakdown
    document_analyses: list[DocumentDeepAnalysis] = Field(default_factory=list)

    # Cross-document analysis
    cross_document_analysis: CrossDocumentAnalysis

    # Enhanced compliance
    enhanced_compliance: dict[str, EnhancedComplianceBreakdown] = Field(
        default_factory=dict
    )  # By regulation

    # Business context
    business_impact: BusinessImpactAssessment
    risk_prioritization: RiskPrioritization


class Document(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    url: str
    title: str | None = None
    product_id: str
    doc_type: DocType
    markdown: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    versions: list[dict[str, Any]] = Field(default_factory=list)
    analysis: DocumentAnalysis | None = None
    extraction: DocumentExtraction | None = None
    locale: str | None = None
    regions: list[Region] = Field(default_factory=list)
    effective_date: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    tier_relevance: TierRelevance = "extended"
