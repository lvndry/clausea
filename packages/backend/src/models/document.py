import json
from datetime import datetime
from typing import Any, Literal

import shortuuid
from pydantic import BaseModel, Field, field_validator


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


class DocumentExtraction(BaseModel):
    """
    Extraction-first, evidence-backed structured facts for a single document.

    This is designed to be used as the ONLY input to downstream summaries, so every
    claim is traceable to an exact quote in the source document.
    """

    version: str = "v1"
    generated_at: datetime = Field(default_factory=datetime.now)
    source_content_hash: str

    data_collected: list[ExtractedTextItem] = Field(default_factory=list)
    data_purposes: list[ExtractedTextItem] = Field(default_factory=list)
    data_collection_details: list[ExtractedDataPurposeLink] = Field(default_factory=list)
    third_party_details: list[ExtractedThirdPartyRecipient] = Field(default_factory=list)
    your_rights: list[ExtractedTextItem] = Field(default_factory=list)
    dangers: list[ExtractedTextItem] = Field(default_factory=list)
    benefits: list[ExtractedTextItem] = Field(default_factory=list)
    recommended_actions: list[ExtractedTextItem] = Field(default_factory=list)


class KeypointWithEvidence(BaseModel):
    """A user-facing keypoint paired with evidence spans."""

    keypoint: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


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


DocType = Literal[
    "privacy_policy",
    "terms_of_service",
    "cookie_policy",
    "terms_of_use",
    "terms_and_conditions",
    "data_processing_agreement",
    "gdpr_policy",
    "copyright_policy",
    "safety_policy",
    "other",
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

    # User Empowerment
    your_rights: list[str] | None = (
        None  # 8-12 rights with explicit instructions: ["Access your data (email, profile) via account.organization.com/privacy", ...]
    )
    dangers: list[str] | None = None  # 5-7 specific concerns with details
    benefits: list[str] | None = None  # 5-7 specific positive privacy protections

    # Actions
    recommended_actions: list[str] | None = None  # 5-8 actionable steps with specific instructions


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
