import json
import logging
from datetime import datetime
from typing import Any, Literal, get_args

import shortuuid
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)

TierRelevance = Literal["core", "extended"]

# Document types considered "core" for tier relevance and query prioritisation.
# Note: the document classifier always emits "terms_of_service" — it never produces
# "terms_of_use" or "terms_and_conditions" as output types. Those aliases were here
# previously but would silently mis-classify every ToS document as "extended" tier.
CORE_DOC_TYPES = {
    "privacy_policy",
    "terms_of_service",
    "cookie_policy",
    "gdpr_policy",
    "community_guidelines",
    "copyright_policy",
    "children_privacy_policy",
    "data_processing_agreement",
    "security_policy",
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

    @model_validator(mode="after")
    def _verified_requires_offsets(self) -> "EvidenceSpan":
        # Without character offsets the quote can't be located in the source text,
        # so it can't be highlighted — and isn't verified.
        if self.start_char is None or self.end_char is None:
            self.verified = False
        return self


class SourceCitation(BaseModel):
    """User-facing source metadata for a verified evidence quote."""

    document_id: str
    document_title: str | None = None
    document_type: str | None = None
    document_url: str
    quote: str
    section_title: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    content_hash: str | None = None
    verified: bool = True


class ExtractedTextItem(BaseModel):
    """An extracted, normalized text item with evidence."""

    value: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedDataPurposeLink(BaseModel):
    """Evidence-backed DataPurposeLink."""

    model_config = ConfigDict(populate_by_name=True)

    data_type: str = Field(validation_alias=AliasChoices("data_type", "value"))
    purposes: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ExtractedThirdPartyRecipient(BaseModel):
    """Evidence-backed ThirdPartyRecipient."""

    recipient: str
    data_shared: list[str] = Field(default_factory=list)
    purpose: str | None = None
    risk_level: Literal["low", "medium", "high"] = "medium"
    evidence: list[EvidenceSpan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# v4 extraction models — richer, purpose-built types
# ---------------------------------------------------------------------------


class ExtractedDataItem(BaseModel):
    """A specific data type collected, with sensitivity and optionality."""

    model_config = ConfigDict(populate_by_name=True)

    data_type: str = Field(validation_alias=AliasChoices("data_type", "value"))
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


TopicStatus = Literal["found", "missing", "not_disclosed", "ambiguous"]
TopicStance = Literal["low_risk", "moderate_risk", "high_risk", "not_disclosed", "mixed"]


class TopicStanceBreakdown(BaseModel):
    """Deterministic per-topic status and risk stance at product level."""

    topic: InsightCategory
    status: TopicStatus
    stance: TopicStance
    topic_score: int | None = Field(default=None, ge=0, le=10)
    rationale: str | None = None
    rationale_key: str | None = None
    rationale_params: dict[str, int | str | None] | None = None
    evidence_count: int | None = None
    document_count: int | None = None
    headline_claim: str | None = None
    supporting_citations: list["TopicSupportCitation"] = Field(default_factory=list)
    conflict_note: str | None = None
    why_it_matters: str | None = None
    recommended_action: str | None = None


class TopicSupportCitation(BaseModel):
    """Compact citation attached to topic overview cards."""

    document_id: str
    document_title: str | None = None
    document_url: str | None = None
    quote: str
    section_title: str | None = None
    verified: bool = True


class DocumentAnalysis(BaseModel):
    """
    Full document analysis — narrative, scoring, and clause-level breakdown.

    All analysis is deep by default: every document gets narrative interpretation,
    dimensional scores, risk verdict, and clause-level critical findings.
    """

    # Narrative and scoring
    summary: str
    scores: dict[str, DocumentAnalysisScores]
    risk_score: int = Field(default=5, ge=0, le=10, description="Overall risk score from 0-10")
    verdict: Literal[
        "very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"
    ] = Field(default="moderate", description="Privacy friendliness level based on risk score")
    grade: Literal["A", "B", "C", "D", "E"] | None = Field(
        default=None, description="A-E grade derived deterministically from risk_score"
    )
    liability_risk: int | None = Field(
        default=None, ge=0, le=10, description="Liability risk score (0-10, for business users)"
    )
    compliance_status: dict[str, int] | None = Field(
        default=None, description="Compliance scores per regulation (e.g., {'GDPR': 8, 'CCPA': 7})"
    )
    keypoints: list[str] | None = None
    keypoints_with_evidence: list[KeypointWithEvidence] | None = None
    applicability: str | None = Field(
        default=None,
        validation_alias=AliasChoices("applicability", "scope"),
        description=(
            "Who and where this policy applies (geography, product line, audience). "
            "Not how much data is collected — that is scores.data_collection_scope. "
            "Examples: 'Global', 'EU-specific', 'Terms for mobile app X only'."
        ),
    )
    privacy_signals: PrivacySignals | None = None
    coverage: list[CoverageItem] | None = None
    contract_clauses: list[str] | None = None

    # Deep analysis fields — always populated (deep is the default, no separate step).
    # String annotations because CriticalClause / DocumentSection / DocumentRiskBreakdown
    # are defined later in this module.
    critical_clauses: "list[CriticalClause] | None" = None
    document_risk_breakdown: "DocumentRiskBreakdown | None" = None
    key_sections: "list[DocumentSection] | None" = None

    # Analysis completeness metadata.
    analysis_completeness: Literal["full", "partial"] = "full"
    coverage_gaps: list[str] = Field(default_factory=list)

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

    data_type: str = Field(examples=["Email address"])
    purposes: list[str] = Field(examples=[["Account creation", "Marketing emails"]])


class ThirdPartyRecipient(BaseModel):
    """Details about a third party that receives user data."""

    recipient: str = Field(examples=["Advertisers", "Analytics providers"])
    data_shared: list[str] = Field(examples=[["email", "browsing history"]])
    purpose: str | None = Field(default=None, examples=["Targeted advertising"])
    risk_level: Literal["low", "medium", "high"] = "medium"


class ProductContradiction(BaseModel):
    """An inconsistency identified between two policy documents."""

    document_a: str
    document_b: str
    description: str
    impact: str


class MetaSummary(BaseModel):
    summary: str
    headline_claim: str | None = Field(
        default=None,
        description=(
            "One human-friendly sentence summarising the product's single most important "
            "privacy posture. Generated by the LLM as part of the product overview."
        ),
    )
    scores: MetaSummaryScores
    risk_score: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Overall risk 0-10; computed server-side from scores, not from LLM",
    )
    verdict: Literal[
        "very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"
    ] = Field(
        default="moderate",
        description="Privacy friendliness; computed server-side from risk_score",
    )
    grade: Literal["A", "B", "C", "D", "E"] | None = Field(
        default=None, description="A-E grade derived deterministically from risk_score"
    )
    keypoints: list[str] = Field(default_factory=list)
    data_collected: list[str] | None = None
    data_purposes: list[str] | None = None
    data_collection_details: list[DataPurposeLink] | None = None
    third_party_details: list[ThirdPartyRecipient] | None = None
    your_rights: list[str] | None = None
    dangers: list[str] | None = None
    benefits: list[str] | None = None
    recommended_actions: list[str] | None = None
    privacy_signals: PrivacySignals | None = None
    compliance_status: dict[str, int] | None = None
    coverage: list[CoverageItem] | None = None
    topic_stances: list[TopicStanceBreakdown] | None = None
    contract_clauses: list[str] | None = None
    contradictions: list[ProductContradiction] | None = None

    @field_validator("keypoints", mode="before")
    @classmethod
    def keypoints_omit_or_null(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [str(x) for x in v if x is not None]

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


# ---------------------------------------------------------------------------
# Consumer TOS-Explainer (plain-English, second-person output for end users)
#
# This is the consumer-facing companion to DocumentAnalysis. Where
# DocumentAnalysis scores a document for operators, ConsumerExplainer turns the
# same gated extraction + analysis into plain English a non-lawyer reads.
#
# These models are populated by free/weak LLMs (the FREE-FIRST cascade), so
# every enum is coerced leniently rather than enforced with strict Literals:
# an unknown value is logged and defaulted instead of discarding the whole
# finding. This mirrors the enum-drift coercion in extraction_service.py.
# ---------------------------------------------------------------------------

# Plain string + lenient coercion, NOT a strict Literal. Weak models drift
# ("severe", "warning", "critical!"); a strict Literal would reject the entire
# parse. We coerce to the nearest valid bucket and log the drift.
ConsumerSeverity = str
ConsumerGrade = str

_VALID_CONSUMER_SEVERITIES: frozenset[str] = frozenset({"critical", "high", "medium", "low"})
_VALID_CONSUMER_GRADES: frozenset[str] = frozenset({"A", "B", "C", "D", "E"})
_VALID_QUOTE_STATUSES: frozenset[str] = frozenset({"from_extraction", "none"})
_VALID_CONFIDENCE_LEVELS: frozenset[str] = frozenset({"high", "medium", "low"})


def _coerce_consumer_severity(value: Any, default: str = "medium") -> str:
    """Coerce a model-emitted severity to one of critical/high/medium/low."""
    if not isinstance(value, str):
        logger.warning(
            "ConsumerExplainer: non-string severity %r, defaulting to %s", value, default
        )
        return default
    candidate = value.strip().lower()
    if candidate in _VALID_CONSUMER_SEVERITIES:
        return candidate
    # Common drift synonyms map to the nearest bucket.
    synonyms = {
        "severe": "critical",
        "blocker": "critical",
        "dangerous": "critical",
        "major": "high",
        "warning": "high",
        "moderate": "medium",
        "minor": "low",
        "info": "low",
        "informational": "low",
    }
    if candidate in synonyms:
        return synonyms[candidate]
    logger.warning("ConsumerExplainer: unknown severity %r, defaulting to %s", value, default)
    return default


class ActionStep(BaseModel):
    """A step the reader can take to protect themselves (e.g. opt out, delete data)."""

    action: str
    applies_to: list[str] = Field(
        default_factory=lambda: ["global"],
        description="Lowercase region codes the step applies to, e.g. ['eu', 'uk']; ['global'] means everyone.",
    )

    @field_validator("applies_to", mode="before")
    @classmethod
    def _normalize_regions(cls, value: Any) -> list[str]:
        items = value if isinstance(value, list) else [value]
        codes: list[str] = []
        for item in items:
            code = str(item).strip().lower()
            if code in {"", "everyone", "all", "worldwide", "anyone"}:
                code = "global"
            if code and code not in codes:
                codes.append(code)
        return codes or ["global"]


class ConsumerCase(BaseModel):
    """One consumer-facing finding: a risk, a data recipient, or a collected data item.

    The same model backs ``watch_out_for``, ``who_gets_your_data`` and
    ``what_they_collect`` so the validator can treat every finding uniformly.

    ``means_for_you`` is the real-world consequence for the reader, not the
    capability. ``quote`` is a verbatim snippet copied from the document's
    extraction; if it is not an exact substring of the extraction the validator
    drops the quote (``quote_status="none"``) but keeps the finding.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(
        validation_alias=AliasChoices("title", "who", "data"),
        description="Short plain label (or the recipient/data name for the typed lists).",
    )
    means_for_you: str = ""
    severity: ConsumerSeverity = "medium"
    classification: str | None = None
    what_they_get: str | None = Field(
        default=None, description="What the recipient receives, for the who_gets_your_data list."
    )
    why: str | None = Field(
        default=None, description="The collection purpose, for the what_they_collect list."
    )
    quote: str | None = None
    quote_status: str = "none"
    citation: SourceCitation | None = None
    citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, value: Any) -> str:
        return _coerce_consumer_severity(value)

    @field_validator("quote_status", mode="before")
    @classmethod
    def _coerce_quote_status(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip().lower() in _VALID_QUOTE_STATUSES:
            return value.strip().lower()
        return "none"


class ConsumerDataItem(ConsumerCase):
    """A data-collection finding for ``what_they_collect``.

    ``linkage_tier`` tells the reader how strongly this data is tied to their
    real identity, and ``sold`` flags data the policy says is sold or shared for
    value. Both are judged by the explainer from the same evidence the rest of
    the finding draws on; they fall back to the conservative reading
    (``linked_to_you``, not sold) when the document is silent.
    """

    linkage_tier: Literal["linked_to_you", "linked_to_device", "not_linked"] = "linked_to_you"
    sold: bool = False


class ConsumerSilentTopic(BaseModel):
    """A topic a reader expects but the evidence does not cover (``silent_on[]``)."""

    topic: str
    why_it_matters: str = ""


class ConsumerContradiction(BaseModel):
    """A cross-document conflict for the product roll-up (``conflicts[]``)."""

    topic: str
    what_one_doc_says: str = ""
    what_another_says: str = ""
    assume: str = ""


class ConsumerRegionVerdict(BaseModel):
    """Per-region rights summary for the product roll-up (``rights_by_region[]``)."""

    region: str
    you_can: list[str] = Field(default_factory=list)
    you_cannot: list[str] = Field(default_factory=list)


class ConsumerExplainer(BaseModel):
    """Plain-English explainer of one document, or a product roll-up, for end users.

    Finding lists are ordered worst-first. ``grade`` is advisory as emitted by
    the model and is re-clamped server-side from ``critical_findings_count`` by
    the validator in analyser.py. For product pages, the service layer further
    reconciles both ``grade`` and ``grade_reason`` to the canonical overview
    grade, so the explainer's grade always matches the overview's deterministic
    risk scoring.
    """

    model_config = ConfigDict(populate_by_name=True)

    is_product_rollup: bool = False

    headline: str = ""
    tl_dr: str = Field(default="", validation_alias=AliasChoices("tl_dr", "bottom_line"))
    grade: ConsumerGrade = "C"
    grade_reason: str = ""
    critical_findings_count: int = 0
    confidence: str = "medium"
    region: str | None = None

    # Worst-first finding lists. The roll-up prompt names the risk list
    # ``biggest_risks``; the per-document prompt names it ``watch_out_for`` — both
    # parse into this one field.
    watch_out_for: list[ConsumerCase] = Field(
        default_factory=list,
        validation_alias=AliasChoices("watch_out_for", "biggest_risks"),
    )
    who_gets_your_data: list[ConsumerCase] = Field(default_factory=list)
    what_they_collect: list[ConsumerDataItem] = Field(default_factory=list)
    good_to_know: list[str] = Field(default_factory=list)
    silent_on: list[ConsumerSilentTopic] = Field(default_factory=list)
    what_you_can_do: list[ActionStep] = Field(default_factory=list)

    # Product roll-up extras (only populated when is_product_rollup is True). The
    # roll-up prompt emits ``conflicts`` and ``rights_by_region``; accept those
    # names as aliases so the roll-up's data isn't dropped on parse.
    the_deal: str | None = None
    contradictions: list[ConsumerContradiction] = Field(
        default_factory=list,
        validation_alias=AliasChoices("contradictions", "conflicts"),
    )
    region_verdicts: list[ConsumerRegionVerdict] = Field(
        default_factory=list,
        validation_alias=AliasChoices("region_verdicts", "rights_by_region"),
    )

    @field_validator("grade", mode="before")
    @classmethod
    def _coerce_grade(cls, value: Any) -> str:
        if not isinstance(value, str):
            logger.warning("ConsumerExplainer: non-string grade %r, defaulting to C", value)
            return "C"
        candidate = value.strip().upper()[:1]
        if candidate in _VALID_CONSUMER_GRADES:
            return candidate
        logger.warning("ConsumerExplainer: unknown grade %r, defaulting to C", value)
        return "C"

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip().lower() in _VALID_CONFIDENCE_LEVELS:
            return value.strip().lower()
        return "medium"

    @field_validator("critical_findings_count", mode="before")
    @classmethod
    def _coerce_count(cls, value: Any) -> int:
        try:
            return max(0, int(value))
        except (ValueError, TypeError):
            return 0

    @field_validator("good_to_know", mode="before")
    @classmethod
    def _coerce_good_to_know(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item is not None]


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
    "security_policy",
    "other",
]


_VALID_DOC_TYPE_VALUES: frozenset[str] = frozenset(get_args(DocType))


def coerce_doc_type_from_classifier(raw: str | None) -> DocType:
    """Normalize classifier output to a valid stored ``doc_type``.

    Unknown labels (for example LLM drift) are stored as ``other`` so substantive
    policy pages stay ingestible. Callers must only invoke this when
    ``is_policy_document`` is true — non-policy pages should not be persisted.
    """
    key = (raw or "other").strip()
    if key in _VALID_DOC_TYPE_VALUES:
        return key  # ty: ignore[invalid-return-type]
    return "other"


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
    strengths: list[str] = Field(description="What they do well.")
    gaps: list[str] = Field(description="What is missing or unclear.")


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
    one_line_summary: str = Field(
        examples=["Spotify collects extensive data for ads but offers strong user rights"]
    )
    headline_claim: str | None = Field(
        default=None,
        description=(
            "One human-friendly sentence summarising the product's single most important "
            "privacy posture, as generated by the LLM."
        ),
    )

    # Core Insights (what users most want to know)
    data_collected: list[str] | None = Field(
        default=None, examples=[["Email", "Listening history", "Location"]]
    )
    data_purposes: list[str] | None = Field(
        default=None, examples=[["Core service", "Advertising", "Analytics"]]
    )
    third_party_sharing: str | None = Field(
        default=None, examples=["Shared with advertisers and analytics partners"]
    )

    # Structured data for Overview redesign
    data_collection_details: list[DataPurposeLink] | None = Field(
        default=None, description="Each data type mapped to its collection purposes."
    )
    third_party_details: list[ThirdPartyRecipient] | None = Field(
        default=None, description="Recipients with their specific sharing details."
    )

    # Top keypoints and document metadata for quick UI
    keypoints: list[str] | None = None
    document_counts: dict[str, int] | None = Field(
        default=None, description="Document counts keyed by total, analyzed, and pending."
    )
    document_types: dict[str, int] | None = None

    # Detailed scoring breakdown (surfaced from MetaSummaryScores)
    detailed_scores: MetaSummaryScores | None = None

    # Compliance status per regulation (e.g., {"GDPR": 8, "CCPA": 7})
    compliance_status: dict[str, int] | None = None

    # Quick-scan privacy signals
    privacy_signals: PrivacySignals | None = None
    topic_stances: list[TopicStanceBreakdown] | None = None

    # User Empowerment
    your_rights: list[str] | None = Field(
        default=None,
        description="8-12 rights with explicit instructions.",
        examples=[["Access your data (email, profile) via account.organization.com/privacy"]],
    )
    dangers: list[str] | None = Field(
        default=None, description="5-7 specific concerns with details."
    )
    benefits: list[str] | None = Field(
        default=None, description="5-7 specific positive privacy protections."
    )

    # Actions
    recommended_actions: list[str] | None = Field(
        default=None, description="5-8 actionable steps with specific instructions."
    )
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
    top_concerns: list[str] | None = Field(default=None, description="Top 3 concerns.")
    summary: str | None = Field(
        default=None, description="User-oriented explanation from analysis."
    )
    keypoints: list[str] | None = Field(
        default=None, description="Key bullet points from analysis."
    )
    keypoints_with_evidence: list[KeypointWithEvidence] | None = Field(
        default=None, description="Optional evidence citations."
    )
    critical_clauses: "list[CriticalClause] | None" = None
    document_risk_breakdown: "DocumentRiskBreakdown | None" = None
    key_sections: "list[DocumentSection] | None" = None

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
            summary_data["critical_clauses"] = doc.analysis.critical_clauses
            summary_data["document_risk_breakdown"] = doc.analysis.document_risk_breakdown
            summary_data["key_sections"] = doc.analysis.key_sections
        else:
            summary_data["summary"] = None
            summary_data["keypoints"] = None
            summary_data["keypoints_with_evidence"] = None
            summary_data["verdict"] = None
            summary_data["risk_score"] = None
            summary_data["critical_clauses"] = None
            summary_data["document_risk_breakdown"] = None
            summary_data["key_sections"] = None

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
    compliance: dict[str, ComplianceBreakdown] | None = Field(
        default=None, description="Compliance breakdown keyed by regulation, e.g. GDPR or CCPA."
    )

    # Complete keypoints (not just top 5)
    all_keypoints: list[str]

    # Document metadata
    documents: list[DocumentSummary]


class CriticalClause(BaseModel):
    """Analysis of a critical clause in a document."""

    # Free-form: the LLM produces specific, high-signal types (e.g. "arbitration_clause",
    # "liability_cap", "ai_training_rights") that a fixed enum can't anticipate. A rigid
    # Literal here rejected the entire DocumentAnalysis on any unlisted value; keeping the
    # specific string preserves the signal (arbitration/biometric/etc. drive consumer risk).
    clause_type: str
    section_title: str | None = None
    quote: str = Field(description="Exact text from the document.")
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"

    @field_validator("risk_level", mode="before")
    @classmethod
    def _coerce_risk_level(cls, value: object) -> str:
        mapping = {"severe": "critical", "moderate": "medium", "minor": "low", "none": "low"}
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"low", "medium", "high", "critical"}:
                return normalized
            if normalized in mapping:
                return mapping[normalized]
        return "medium"

    plain_english: str = Field(default="", description="What this means to a non-lawyer.")
    why_notable: str = Field(default="", description="Why this clause is significant.")
    # Legacy alias — kept for backward compatibility, maps to plain_english
    analysis: str = ""
    compliance_impact: list[str] = Field(default_factory=list)


class DocumentSection(BaseModel):
    """Important section of a document with analysis."""

    section_title: str
    content: str = Field(description="Full text of the section.")
    importance: Literal["low", "medium", "high", "critical"]
    analysis: str = Field(description="What this section means.")
    related_clauses: list[str] = Field(
        default_factory=list,
        description="IDs or indices of related critical clauses.",
    )


class DocumentRiskBreakdown(BaseModel):
    """Detailed risk assessment for a document."""

    overall_risk: int = Field(ge=0, le=10)
    risk_by_category: dict[str, int] = Field(
        default_factory=dict,
        examples=[{"data_sharing": 8, "retention": 5}],
    )

    @model_validator(mode="before")
    @classmethod
    def _derive_overall_risk(cls, data: Any) -> Any:
        """Tolerate cheaper models that omit overall_risk but provide per-category risks.

        Without this, a single missing nested field discards the entire document
        analysis. When overall_risk is absent we derive it from risk_by_category
        (mean), falling back to a neutral 5 only when no category signal exists.
        """
        if isinstance(data, dict) and data.get("overall_risk") in (None, ""):
            categories = data.get("risk_by_category") or {}
            values = [v for v in categories.values() if isinstance(v, int | float)]
            data["overall_risk"] = round(sum(values) / len(values)) if values else 5
        return data

    top_concerns: list[str] = Field(default_factory=list, description="Specific concerns.")
    positive_protections: list[str] = Field(default_factory=list, description="Good practices.")
    missing_information: list[str] = Field(
        default_factory=list, description="What is not mentioned."
    )
    applicability: str | None = Field(
        default=None,
        validation_alias=AliasChoices("applicability", "scope"),
        description=(
            "Who/where this document applies. Copied from top-level DocumentAnalysis.applicability "
            "when the model omits it inside the breakdown."
        ),
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
        default_factory=list,
        description="Important sections with quotes.",
    )


class DocumentContradiction(BaseModel):
    """Identified contradiction between documents."""

    document_a: str = Field(description="Document ID or name.")
    document_b: str
    contradiction_type: str = Field(examples=["data_sharing", "retention"])
    description: str
    document_a_statement: str = Field(description="What document A says.")
    document_b_statement: str = Field(description="What document B says.")
    impact: str = Field(description="Risk or legal impact.")
    recommendation: str = Field(description="How to resolve.")


class DocumentRelationship(BaseModel):
    """Relationship between documents."""

    document_a: str
    document_b: str
    relationship_type: Literal["references", "supersedes", "complements", "conflicts"]
    description: str
    evidence: str = Field(description="Quote or reference supporting the relationship.")


class InformationGap(BaseModel):
    """A structured information gap — a policy area users expect but no document addresses."""

    topic: str
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    regulatory_consequence: str | None = None
    recommendation: str | None = None


class CrossDocumentAnalysis(BaseModel):
    """Analysis across all documents."""

    contradictions: list[DocumentContradiction] = Field(default_factory=list)
    information_gaps: list[InformationGap] = Field(default_factory=list)
    document_relationships: list[DocumentRelationship] = Field(default_factory=list)

    @field_validator("information_gaps", mode="before")
    @classmethod
    def coerce_information_gaps(cls, v: object) -> list[object]:
        """Accept both legacy list[str] and new list[dict] from cached data."""
        if not v:
            return []
        result = []
        for item in v:  # ty: ignore[not-iterable]
            if isinstance(item, str):
                result.append({"topic": item, "severity": "medium"})
            else:
                result.append(item)
        return result


class ComplianceViolation(BaseModel):
    """Specific compliance violation."""

    requirement: str = Field(examples=["GDPR Article 15 - Right of access"])
    violation_type: Literal["missing", "unclear", "non_compliant"]
    description: str = Field(description="What is wrong.")
    severity: Literal["low", "medium", "high", "critical"]
    remediation: str = Field(description="How to fix.")


class EnhancedComplianceBreakdown(BaseModel):
    """Enhanced compliance analysis per regulation."""

    regulation: str = Field(examples=["GDPR", "CCPA"])
    score: int = Field(ge=0, le=10)
    status: Literal["Compliant", "Partially Compliant", "Non-Compliant", "Unknown"]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    violations: list[ComplianceViolation] = Field(
        default_factory=list, description="Specific violations."
    )
    remediation_recommendations: list[str] = Field(default_factory=list)
    detailed_analysis: str = Field(description="Comprehensive explanation.")


class PrioritizedAction(BaseModel):
    """Action item with priority."""

    action: str
    priority: Literal["critical", "high", "medium", "low"]
    rationale: str
    deadline: str | None = Field(default=None, examples=["Immediate", "Within 30 days"])


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
    financial_impact: str = Field(description="Potential financial consequences.")
    reputational_risk: str = Field(description="Reputational implications.")
    operational_risk: str = Field(description="Operational implications.")
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


# ---------------------------------------------------------------------------
# Professional-grade deep analysis models
# ---------------------------------------------------------------------------


class ProcurementDecision(BaseModel):
    """Go/no-go recommendation for vendor procurement."""

    decision: Literal["approved", "conditionally_approved", "escalate_to_legal", "do_not_use"]
    overall_risk_rating: Literal["low", "medium", "high", "critical"]
    conditions: list[str] = Field(default_factory=list)
    executive_brief: str
    blocking_issues: list[str] = Field(default_factory=list)


class SubprocessorEntry(BaseModel):
    """A named subprocessor with geographic and transfer details."""

    name: str
    country: str
    data_categories: list[str] = Field(default_factory=list)
    transfer_mechanism: (
        Literal["adequacy_decision", "scc", "bcr", "unknown", "not_applicable"] | None
    ) = None
    risk_note: str | None = None


class LegalBasisEntry(BaseModel):
    """Legal basis claimed for a specific data category."""

    data_category: str
    legal_basis: str
    adequacy: Literal["adequate", "questionable", "missing"] = "adequate"
    note: str | None = None


class DataProcessingProfile(BaseModel):
    """Controller/processor classification, legal basis mapping, and subprocessor chain."""

    controller_processor_classification: Literal[
        "controller", "processor", "joint_controller", "unclear"
    ]
    classification_rationale: str
    legal_basis_mapping: list[LegalBasisEntry] = Field(default_factory=list)
    subprocessors: list[SubprocessorEntry] = Field(default_factory=list)
    data_residency: list[str] = Field(default_factory=list)
    cross_border_transfers: bool = False
    transfer_mechanisms_noted: list[str] = Field(default_factory=list)


class ArticleComplianceCheck(BaseModel):
    """Per-article compliance status for a regulation."""

    article: str
    requirement: str
    status: Literal["met", "partial", "missing", "not_applicable", "unclear"]
    evidence: str | None = None
    gap: str | None = None


class RegulationArticleBreakdown(BaseModel):
    """Article-level compliance breakdown for a single regulation."""

    regulation: str
    score: int = Field(ge=0, le=10)
    status: Literal["Compliant", "Partially Compliant", "Non-Compliant", "Unknown"]
    article_checks: list[ArticleComplianceCheck] = Field(default_factory=list)
    critical_gaps: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    detailed_analysis: str


class RiskRegisterItem(BaseModel):
    """A structured risk item with source, severity, and remediation guidance."""

    id: str
    title: str
    description: str
    source_document: str
    clause_reference: str | None = None
    verbatim_quote: str | None = None
    severity: Literal["critical", "high", "medium", "low"]
    likelihood: Literal["high", "medium", "low"]
    regulatory_exposure: list[str] = Field(default_factory=list)
    blocking: bool = False
    remediation_type: Literal[
        "contractual_negotiation",
        "technical_controls",
        "user_restriction",
        "dpa_required",
        "accept_risk",
        "reject_vendor",
        "policy_update",
    ]
    recommended_action: str
    suggested_owner: Literal["Legal", "DPO", "IT/Security", "Procurement", "HR", "CISO"]


class ContractClauseReview(BaseModel):
    """Compliance-oriented review of a specific contract clause."""

    clause_type: str
    section_reference: str | None = None
    verbatim_quote: str
    plain_english: str
    standard_assessment: Literal[
        "standard_industry", "unusual", "one_sided", "potentially_unlawful"
    ]
    risk_if_accepted: str
    negotiation_lever: str | None = None
    recommended_redline: str | None = None


class WorkforceDataAssessment(BaseModel):
    """Assessment of risks specific to employee / workforce personal data."""

    applicable: bool
    risk_level: Literal["low", "medium", "high", "critical"] | None = None
    employee_data_categories_mentioned: list[str] = Field(default_factory=list)
    monitoring_risks: list[str] = Field(default_factory=list)
    hr_specific_concerns: list[str] = Field(default_factory=list)
    labor_law_considerations: list[str] = Field(default_factory=list)
    recommendation: str | None = None


class DPIATriggerAssessment(BaseModel):
    """Assessment of whether a Data Protection Impact Assessment is required."""

    dpia_required: Literal["yes", "no", "likely", "unclear"]
    triggering_factors: list[str] = Field(default_factory=list)
    recommended_scope: str | None = None
    note: str | None = None


class SecurityPosture(BaseModel):
    """Security practices and incident response commitments described in the documents."""

    certifications_claimed: list[str] = Field(default_factory=list)
    encryption_at_rest: Literal["confirmed", "partial", "not_mentioned"] = "not_mentioned"
    encryption_in_transit: Literal["confirmed", "partial", "not_mentioned"] = "not_mentioned"
    breach_notification_commitment: str | None = None
    breach_notification_timeline: str | None = None
    audit_rights: bool = False
    data_deletion_on_termination: Literal["confirmed", "unclear", "not_mentioned"] = "not_mentioned"
    overall_security_assessment: str


class RemediationItem(BaseModel):
    """A single prioritized action in the remediation roadmap."""

    priority: Literal["critical", "high", "medium", "low"]
    action: str
    rationale: str
    suggested_owner: str
    timeline: str | None = None
    blocking: bool = False
    related_risk_ids: list[str] = Field(default_factory=list)


class ProductDeepAnalysis(BaseModel):
    """
    Level 3: Professional-grade compliance audit.
    Designed for compliance officers, DPOs, and legal teams performing vendor due diligence.
    """

    # Level 2 (context)
    analysis: ProductAnalysis

    # Document-by-document deep breakdown
    document_analyses: list[DocumentDeepAnalysis] = Field(default_factory=list)

    # Cross-document analysis
    cross_document_analysis: CrossDocumentAnalysis

    # === Professional-grade sections ===

    # Go/no-go procurement recommendation
    procurement_decision: ProcurementDecision | None = None

    # Controller/processor classification, legal basis, subprocessor chain
    data_processing_profile: DataProcessingProfile | None = None

    # Article-level compliance breakdown per regulation
    article_compliance: dict[str, RegulationArticleBreakdown] = Field(default_factory=dict)

    # Structured risk register (source, quote, owner, blocking status)
    risk_register: list[RiskRegisterItem] = Field(default_factory=list)

    # Contract clause review with standard/unusual flag and negotiation levers
    contract_clause_review: list[ContractClauseReview] = Field(default_factory=list)

    # Employee / workforce data specific risks
    workforce_data_assessment: WorkforceDataAssessment | None = None

    # DPIA trigger assessment
    dpia_trigger: DPIATriggerAssessment | None = None

    # Security certifications, encryption, breach notification
    security_posture: SecurityPosture | None = None

    # Prioritized remediation roadmap with owners and timelines
    remediation_roadmap: list[RemediationItem] = Field(default_factory=list)

    # Business impact
    business_impact: BusinessImpactAssessment

    # Kept for backward compatibility
    enhanced_compliance: dict[str, EnhancedComplianceBreakdown] = Field(default_factory=dict)
    risk_prioritization: RiskPrioritization = Field(default_factory=RiskPrioritization)


class Document(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    url: str
    title: str | None = None
    product_id: str
    # Canonical document rows can be shared across multiple products.
    # product_id remains the canonical owner for backward compatibility, while
    # product_ids tracks all linked products that can reuse this document.
    product_ids: list[str] = Field(default_factory=list)
    doc_type: DocType = "other"
    markdown: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    versions: list[dict[str, Any]] = Field(default_factory=list)
    analysis: DocumentAnalysis | None = None
    extraction: DocumentExtraction | None = None
    consumer_explainer: ConsumerExplainer | None = None
    locale: str | None = None
    regions: list[Region] = Field(default_factory=list)
    effective_date: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    # Last time this document row was written (stored or updated). Drives crawl
    # resume: a retried crawl skips re-fetching docs written within the resume
    # freshness window, while older docs are still re-fetched for change detection.
    updated_at: datetime = Field(default_factory=datetime.now)
    tier_relevance: TierRelevance = "extended"
    content_hash: str | None = None
    analysis_error: str | None = None

    @model_validator(mode="after")
    def _ensure_product_membership(self) -> "Document":
        linked: list[str] = []
        for candidate in [self.product_id, *self.product_ids]:
            if not isinstance(candidate, str):
                continue
            normalized = candidate.strip()
            if normalized and normalized not in linked:
                linked.append(normalized)

        if not linked:
            linked = [self.product_id]

        # Keep product_id as the canonical first member.
        self.product_id = linked[0]
        self.product_ids = linked
        return self

    def is_linked_to_product(self, product_id: str) -> bool:
        return product_id in self.product_ids


# Resolve forward references now that all classes are defined.
DocumentAnalysis.model_rebuild()
