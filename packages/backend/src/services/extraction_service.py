"""Evidence-first extraction for policy documents (v4).

Extracts structured facts from a document WITH evidence (exact quotes),
so downstream summaries can be generated from extracted facts only.

Clusters (per chunk, all run in parallel):
  Cluster 1 — Data Practices:      data_collected, data_purposes, retention_policies,
                                    security_measures, cookies_and_trackers
  Cluster 2 — Sharing & Transfers: third_party_details, international_transfers,
                                    government_access, corporate_family_sharing
  Cluster 3 — Rights & AI:         user_rights, consent_mechanisms, account_lifecycle,
                                    ai_usage, children_policy
  Cluster 4 — Legal Terms & Scope: liability, dispute_resolution, content_ownership,
                                    scope_expansion, indemnification,
                                    termination_consequences, dangers, benefits,
                                    recommended_actions

4 parallel calls per chunk — total latency ≈ one serial call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, Field

from src.core.logging import get_logger
from src.llm import (
    EscalationValidator,
    SupportedModel,
    acompletion_with_escalation,
    acompletion_with_fallback,
)
from src.models.document import (
    Document,
    DocumentExtraction,
    EvidenceSpan,
    ExtractedAIUsage,
    ExtractedChildrenPolicy,
    ExtractedContentOwnership,
    ExtractedCookieTracker,
    ExtractedCorporateFamilySharing,
    ExtractedDataItem,
    ExtractedDataPurposeLink,
    ExtractedDisputeResolution,
    ExtractedGovernmentAccess,
    ExtractedInternationalTransfer,
    ExtractedLiability,
    ExtractedRetentionRule,
    ExtractedScopeExpansion,
    ExtractedTextItem,
    ExtractedThirdPartyRecipient,
    ExtractedUserRight,
    PrivacySignals,
)
from src.utils.cancellation import CancellationToken

logger = get_logger(__name__)

_EXTRACTION_RESILIENCE: list[SupportedModel] = ["gemini-2.5-flash"]
_EXTRACTION_PRIMARY: list[SupportedModel] = ["gpt-5-mini"] + _EXTRACTION_RESILIENCE
_EXTRACTION_ESCALATION: list[SupportedModel] = ["gpt-5.4-mini"] + _EXTRACTION_RESILIENCE

_COMPLEX_DOC_LENGTH_THRESHOLD: int = 50_000
_COMPLEX_DOC_TYPES: frozenset[str] = frozenset(
    {"terms_of_service", "data_processing_agreement", "terms_and_conditions"}
)

_CLUSTER_REQUIRED_KEYS: dict[str, list[str]] = {
    "data_practices": [
        "data_collected",
        "data_purposes",
        "retention_policies",
        "security_measures",
    ],
    "sharing_transfers": ["third_party_details", "international_transfers", "government_access"],
    "rights_ai": ["user_rights", "consent_mechanisms", "account_lifecycle", "ai_usage"],
    "legal_scope": ["liability", "dispute_resolution", "content_ownership", "scope_expansion"],
}


def _extraction_validator(cluster_name: str) -> EscalationValidator:
    required = _CLUSTER_REQUIRED_KEYS.get(cluster_name, [])

    def validate(content: str) -> bool:
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                return False
            if required and not all(k in data for k in required):
                return False
            return any(
                isinstance(data.get(k), list) and len(data[k]) > 0
                for k in (required if required else data)
            )
        except (json.JSONDecodeError, AttributeError):
            return False

    return validate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_content_hash(document: Document) -> str:
    content = f"{document.text}{document.doc_type}"
    return hashlib.sha256(content.encode()).hexdigest()


def _split_on_sentence_boundary(text: str, max_len: int) -> int:
    window = text[:max_len]
    for sep in (". ", ".\n", "? ", "! ", ";\n", "\n\n", "\n", " "):
        idx = window.rfind(sep)
        if idx > max_len // 3:
            return idx + len(sep)
    return max_len


def _chunk_text(text: str, *, chunk_size: int = 8000, overlap: int = 800) -> list[str]:
    if not text:
        return []
    if chunk_size <= 0:
        return [text]
    overlap = max(0, min(overlap, chunk_size - 1))

    parts = re.split(r"(?m)^(#{1,6}\s+.*)", text)
    has_headers = len(parts) > 1

    if has_headers:
        sections: list[str] = []
        current = parts[0]
        for i in range(1, len(parts), 2):
            header = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            section = header + body
            if current and len(current) + len(section) > chunk_size:
                sections.append(current)
                current = section
            else:
                current += section
        if current:
            sections.append(current)
    else:
        paragraphs = re.split(r"\n{2,}", text)
        sections = []
        current = ""
        for para in paragraphs:
            candidate = (current + "\n\n" + para) if current else para
            if len(candidate) > chunk_size and current:
                sections.append(current)
                current = para
            else:
                current = candidate
        if current:
            sections.append(current)

    final_chunks: list[str] = []
    for section in sections:
        if len(section) <= chunk_size:
            final_chunks.append(section)
            continue
        start = 0
        n = len(section)
        while start < n:
            remaining = n - start
            if remaining <= chunk_size:
                final_chunks.append(section[start:])
                break
            split_at = _split_on_sentence_boundary(section[start:], chunk_size)
            final_chunks.append(section[start : start + split_at])
            start = max(start + 1, start + split_at - overlap)

    return final_chunks


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _normalize_quotes(s: str) -> str:
    return (
        s.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )


def _resolve_quote_offsets(haystack: str, quote: str) -> tuple[int | None, int | None, bool]:
    if not haystack or not quote:
        return None, None, False

    idx = haystack.find(quote)
    if idx != -1:
        return idx, idx + len(quote), True

    collapsed_h = _collapse_ws(haystack)
    collapsed_q = _collapse_ws(quote)
    if collapsed_q and collapsed_q in collapsed_h:
        return None, None, True

    norm_h = _normalize_quotes(collapsed_h)
    norm_q = _normalize_quotes(collapsed_q)
    if norm_q and norm_q in norm_h:
        return None, None, True

    if len(quote) >= 40:
        target = _collapse_ws(quote)
        window = len(target) * 3 // 4
        if window >= 30:
            for i in range(len(target) - window + 1):
                fragment = target[i : i + window]
                if fragment in collapsed_h:
                    return None, None, True

    return None, None, False


def _make_evidence(document: Document, content_hash: str, quote: str) -> EvidenceSpan:
    start_char, end_char, verified = _resolve_quote_offsets(document.text, quote)
    return EvidenceSpan(
        document_id=document.id,
        url=document.url,
        content_hash=content_hash,
        quote=quote,
        start_char=start_char,
        end_char=end_char,
        section_title=None,
        verified=verified,
    )


# ---------------------------------------------------------------------------
# Internal Pydantic models — LLM response shapes per cluster
# ---------------------------------------------------------------------------


class _Item(BaseModel):
    value: str
    quote: str


class _DataItem(BaseModel):
    data_type: str
    sensitivity: str = "medium"
    required: str = "unclear"
    quote: str


class _PurposeLink(BaseModel):
    data_type: str
    purposes: list[str] = Field(default_factory=list)
    legal_basis: str | None = None
    quote: str


class _RetentionRule(BaseModel):
    data_scope: str
    duration: str
    conditions: str | None = None
    quote: str


class _CookieTracker(BaseModel):
    name_or_type: str
    category: str = "other"
    duration: str | None = None
    third_party: bool = False
    opt_out_mechanism: str | None = None
    quote: str


class _ThirdParty(BaseModel):
    recipient: str
    data_shared: list[str] = Field(default_factory=list)
    purpose: str | None = None
    risk_level: str | None = None
    quote: str


class _InternationalTransfer(BaseModel):
    destination: str
    mechanism: str | None = None
    data_types: list[str] = Field(default_factory=list)
    quote: str


class _GovernmentAccess(BaseModel):
    authority_type: str
    conditions: str
    data_scope: str | None = None
    quote: str


class _CorporateFamily(BaseModel):
    entities: list[str] = Field(default_factory=list)
    data_shared: list[str] = Field(default_factory=list)
    purpose: str | None = None
    quote: str


class _UserRight(BaseModel):
    right_type: str
    description: str
    mechanism: str | None = None
    quote: str


class _AIUsage(BaseModel):
    usage_type: str
    description: str
    data_involved: list[str] = Field(default_factory=list)
    opt_out_available: str = "unclear"
    opt_out_mechanism: str | None = None
    consequences: str | None = None
    quote: str


class _ChildrenPolicy(BaseModel):
    minimum_age: int | None = None
    parental_consent_required: bool = False
    special_protections: str | None = None
    quote: str | None = None


class _Liability(BaseModel):
    scope: str
    limitation_type: str
    description: str
    extends_beyond_product: bool = False
    quote: str


class _DisputeResolution(BaseModel):
    mechanism: str
    class_action_waiver: bool = False
    jury_trial_waiver: bool = False
    venue: str | None = None
    governing_law: str | None = None
    description: str | None = None
    quote: str


class _ContentOwnership(BaseModel):
    ownership_type: str
    scope: str
    description: str
    quote: str


class _ScopeExpansion(BaseModel):
    scope_type: str
    description: str
    entities_affected: list[str] = Field(default_factory=list)
    quote: str


class _PrivacySignals(BaseModel):
    sells_data: str | None = None
    sells_data_quote: str | None = None
    cross_site_tracking: str | None = None
    cross_site_tracking_quote: str | None = None
    account_deletion: str | None = None
    account_deletion_quote: str | None = None
    data_retention_summary: str | None = None
    data_retention_quote: str | None = None
    consent_model: str | None = None
    consent_model_quote: str | None = None
    ai_training_on_user_data: str | None = None
    ai_training_quote: str | None = None
    breach_notification: str | None = None
    breach_notification_quote: str | None = None
    data_minimization: str | None = None
    data_minimization_quote: str | None = None
    children_data_collection: str | None = None
    children_data_collection_quote: str | None = None


# --- Cluster result shapes ---


class _ClusterDataPractices(BaseModel):
    data_collected: list[_DataItem] = Field(default_factory=list)
    data_purposes: list[_PurposeLink] = Field(default_factory=list)
    retention_policies: list[_RetentionRule] = Field(default_factory=list)
    security_measures: list[_Item] = Field(default_factory=list)
    cookies_and_trackers: list[_CookieTracker] = Field(default_factory=list)


class _ClusterSharingTransfers(BaseModel):
    third_party_details: list[_ThirdParty] = Field(default_factory=list)
    international_transfers: list[_InternationalTransfer] = Field(default_factory=list)
    government_access: list[_GovernmentAccess] = Field(default_factory=list)
    corporate_family_sharing: list[_CorporateFamily] = Field(default_factory=list)


class _ClusterRightsAI(BaseModel):
    user_rights: list[_UserRight] = Field(default_factory=list)
    consent_mechanisms: list[_Item] = Field(default_factory=list)
    account_lifecycle: list[_Item] = Field(default_factory=list)
    ai_usage: list[_AIUsage] = Field(default_factory=list)
    children_policy: _ChildrenPolicy | None = None
    privacy_signals: _PrivacySignals | None = None


class _ClusterLegalScope(BaseModel):
    liability: list[_Liability] = Field(default_factory=list)
    dispute_resolution: list[_DisputeResolution] = Field(default_factory=list)
    content_ownership: list[_ContentOwnership] = Field(default_factory=list)
    scope_expansion: list[_ScopeExpansion] = Field(default_factory=list)
    indemnification: list[_Item] = Field(default_factory=list)
    termination_consequences: list[_Item] = Field(default_factory=list)
    dangers: list[_Item] = Field(default_factory=list)
    benefits: list[_Item] = Field(default_factory=list)
    recommended_actions: list[_Item] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are an expert legal-document information extractor.

Your job is to extract structured facts ONLY from the provided text chunk.

Critical rules:
- Only extract items explicitly present in the text chunk.
- For every extracted item, provide an evidence quote that is an EXACT substring of the provided chunk.
- If a field is not present, return an empty list for that field.
- Do not paraphrase evidence quotes; copy exact text.
"""

_CLUSTER_SPECS: dict[str, tuple[dict[str, Any], str]] = {}


def _build_cluster_specs() -> None:
    """Build schema hints and instruction notes for each cluster."""

    # --- Cluster 1: Data Practices ---
    _CLUSTER_SPECS["data_practices"] = (
        {
            "data_collected": [
                {
                    "data_type": "Email address",
                    "sensitivity": "low | medium | high | sensitive",
                    "required": "required | optional | unclear",
                    "quote": "exact quote",
                }
            ],
            "data_purposes": [
                {
                    "data_type": "Email address",
                    "purposes": ["Account creation", "Marketing"],
                    "legal_basis": "consent | legitimate_interest | contract | null",
                    "quote": "exact quote",
                }
            ],
            "retention_policies": [
                {
                    "data_scope": "Account data",
                    "duration": "30 days after deletion",
                    "conditions": "After account closure or null",
                    "quote": "exact quote",
                }
            ],
            "security_measures": [
                {"value": "Encryption in transit and at rest", "quote": "exact quote"}
            ],
            "cookies_and_trackers": [
                {
                    "name_or_type": "Google Analytics",
                    "category": "essential | analytics | advertising | social | other",
                    "duration": "2 years or null",
                    "third_party": True,
                    "opt_out_mechanism": "Browser settings or null",
                    "quote": "exact quote",
                }
            ],
        },
        (
            "Extract ALL of the following from this chunk:\n"
            "1. DATA COLLECTED: every data type mentioned (email, IP, location, biometric, health, financial, etc.).\n"
            "   Classify sensitivity: low (public info), medium (PII), high (financial/precise location), sensitive (biometric/health/genetic/racial/religious).\n"
            "   Note whether required or optional for the service.\n"
            "2. DATA PURPOSES: link each data type to its purposes. Include legal basis if stated (consent, legitimate interest, contract).\n"
            "3. RETENTION: specific durations, conditions, deletion timelines per data scope.\n"
            "4. SECURITY: encryption, access controls, audits, certifications, breach response.\n"
            "5. COOKIES & TRACKERS: specific cookies, pixels, SDKs, fingerprinting. Include category, duration, whether third-party, and opt-out mechanism if stated."
        ),
    )

    # --- Cluster 2: Sharing & Transfers ---
    _CLUSTER_SPECS["sharing_transfers"] = (
        {
            "third_party_details": [
                {
                    "recipient": "Advertisers",
                    "data_shared": ["email", "location data"],
                    "purpose": "Targeted advertising",
                    "risk_level": "low | medium | high",
                    "quote": "exact quote",
                }
            ],
            "international_transfers": [
                {
                    "destination": "United States",
                    "mechanism": "SCC|adequacy_decision|consent|null",
                    "data_types": ["email", "usage data"],
                    "quote": "exact quote",
                }
            ],
            "government_access": [
                {
                    "authority_type": "Law enforcement",
                    "conditions": "Valid court order or subpoena",
                    "data_scope": "str|null",
                    "quote": "exact quote",
                }
            ],
            "corporate_family_sharing": [
                {
                    "entities": ["Meta Platforms", "Instagram", "WhatsApp"],
                    "data_shared": ["account info", "usage data"],
                    "purpose": "Cross-platform analytics",
                    "quote": "exact quote",
                }
            ],
        },
        (
            "Extract ALL of the following from this chunk:\n"
            "1. THIRD-PARTY SHARING: who receives data, what data, why, risk level (low/medium/high).\n"
            "   Include service providers, advertisers, analytics partners, business partners.\n"
            "2. INTERNATIONAL TRANSFERS: where data flows geographically. Include the legal transfer mechanism if stated\n"
            "   (Standard Contractual Clauses, adequacy decisions, binding corporate rules, user consent).\n"
            "3. GOVERNMENT / LAW ENFORCEMENT ACCESS: under what conditions data is shared with authorities.\n"
            "   Include the legal standard required (court order, subpoena, national security letter, voluntary).\n"
            "4. CORPORATE FAMILY SHARING: data shared with parent companies, subsidiaries, affiliates.\n"
            "   Name specific entities when mentioned. Note if agreeing to one service shares data with the whole corporate group."
        ),
    )

    # --- Cluster 3: Rights & AI ---
    _CLUSTER_SPECS["rights_ai"] = (
        {
            "user_rights": [
                {
                    "right_type": "Deletion",
                    "description": "Delete your account and associated data",
                    "mechanism": "Settings > Privacy > Delete Account, or email privacy@example.com",
                    "quote": "exact quote",
                }
            ],
            "consent_mechanisms": [
                {
                    "value": "Opt-out of marketing emails via unsubscribe link",
                    "quote": "exact quote",
                }
            ],
            "account_lifecycle": [
                {"value": "Data deleted 30 days after account closure", "quote": "exact quote"}
            ],
            "ai_usage": [
                {
                    "usage_type": "training_on_user_data | automated_decisions | profiling | content_generation | recommendation | moderation | other",
                    "description": "User content used to train language models",
                    "data_involved": ["text messages", "uploaded files"],
                    "opt_out_available": "yes | no | unclear",
                    "opt_out_mechanism": "Settings > Privacy > AI Training or null",
                    "consequences": "AI features may be less personalized or null",
                    "quote": "exact quote",
                }
            ],
            "children_policy": {
                "minimum_age": 13,
                "parental_consent_required": True,
                "special_protections": "Limited data collection for under-16s or null",
                "quote": "exact quote or null",
            },
            "privacy_signals": {
                "sells_data": "yes|no|unclear|null",
                "sells_data_quote": "str|null",
                "cross_site_tracking": "yes|no|unclear|null",
                "cross_site_tracking_quote": "str|null",
                "account_deletion": "self_service|request_required|not_specified|null",
                "account_deletion_quote": "str|null",
                "data_retention_summary": "str|null",
                "data_retention_quote": "str|null",
                "consent_model": "opt_in|opt_out|mixed|not_specified|null",
                "consent_model_quote": "str|null",
                "ai_training_on_user_data": "yes|no|unclear|null",
                "ai_training_quote": "str|null",
                "breach_notification": "yes|no|not_specified|null",
                "breach_notification_quote": "str|null",
                "data_minimization": "yes|no|unclear|null",
                "data_minimization_quote": "str|null",
                "children_data_collection": "yes|no|not_specified|null",
                "children_data_collection_quote": "str|null",
            },
        },
        (
            "Extract ALL of the following from this chunk:\n"
            "1. USER RIGHTS: access, correction, deletion, portability, objection, restriction, withdrawal of consent.\n"
            "   Include the MECHANISM (URL, settings path, email address) to exercise each right.\n"
            "2. CONSENT MECHANISMS: how consent is obtained, withdrawn, managed. Granularity of choices.\n"
            "3. ACCOUNT LIFECYCLE: what happens to data on account closure/deletion/inactivity.\n"
            "   Include data portability/export options, deletion timelines, what survives deletion.\n"
            "4. AI / PROFILING / AUTOMATED DECISIONS:\n"
            "   - Is user data/content used to TRAIN AI models? Can users opt out?\n"
            "   - Are automated decisions made about users (content moderation, pricing, eligibility)?\n"
            "   - Is profiling performed? What profiles are built and for what purpose?\n"
            "   - Are AI-generated outputs based on user data (voice cloning, style mimicking)?\n"
            "5. CHILDREN & AGE: minimum age, COPPA/children's privacy, parental consent, special protections for minors.\n"
            "6. PRIVACY SIGNALS: only set a field if the chunk EXPLICITLY mentions it, null otherwise."
        ),
    )

    # --- Cluster 4: Legal Terms & Scope ---
    _CLUSTER_SPECS["legal_scope"] = (
        {
            "liability": [
                {
                    "scope": "Service use and all affiliated properties",
                    "limitation_type": "cap | waiver | exclusion | indemnification",
                    "description": "Liability limited to fees paid in last 12 months",
                    "extends_beyond_product": False,
                    "quote": "exact quote",
                }
            ],
            "dispute_resolution": [
                {
                    "mechanism": "arbitration | litigation | mediation | other",
                    "class_action_waiver": True,
                    "jury_trial_waiver": True,
                    "venue": "Delaware or null",
                    "governing_law": "State of California or null",
                    "description": "Binding arbitration with opt-out window or null",
                    "quote": "exact quote",
                }
            ],
            "content_ownership": [
                {
                    "ownership_type": "license_to_company | user_retains | company_owns | ai_training_rights | likeness_rights | other",
                    "scope": "Perpetual, irrevocable, worldwide, sublicensable license",
                    "description": "Company may use uploaded content to train AI models and create derivative works",
                    "quote": "exact quote",
                }
            ],
            "scope_expansion": [
                {
                    "scope_type": "cross_entity | survival_clause | unilateral_modification | binding_heirs | physical_world | other",
                    "description": "Terms apply to all subsidiaries including theme parks and retail stores",
                    "entities_affected": ["Disney+", "Disneyland", "ESPN"],
                    "quote": "exact quote",
                }
            ],
            "indemnification": [
                {
                    "value": "User indemnifies company against all claims from user content",
                    "quote": "exact quote",
                }
            ],
            "termination_consequences": [
                {
                    "value": "Company may delete all content 30 days after termination",
                    "quote": "exact quote",
                }
            ],
            "dangers": [
                {
                    "value": "No cap on liability for user-generated content claims",
                    "quote": "exact quote",
                }
            ],
            "benefits": [
                {"value": "30-day opt-out window for arbitration clause", "quote": "exact quote"}
            ],
            "recommended_actions": [
                {
                    "value": "Send opt-out notice to arbitration@example.com within 30 days",
                    "quote": "exact quote",
                }
            ],
        },
        (
            "Extract ALL of the following from this chunk:\n"
            "1. LIABILITY: limitations, caps, waivers, exclusions.\n"
            "   CRITICAL: flag if liability waivers EXTEND BEYOND the digital product — e.g. waiving\n"
            "   liability for physical injury at venues, medical claims, or unrelated subsidiary services.\n"
            "   Set extends_beyond_product=true for these.\n"
            "2. DISPUTE RESOLUTION: arbitration clauses, class action waivers, jury trial waivers,\n"
            "   venue/forum requirements, mass arbitration rules, opt-out windows.\n"
            "   Include governing law/jurisdiction.\n"
            "3. CONTENT OWNERSHIP / IP: what rights the company claims over user content.\n"
            "   Flag perpetual/irrevocable/sublicensable licenses, AI training rights over user content,\n"
            "   rights to user's likeness/voice/image, and derivative work rights.\n"
            "4. SCOPE EXPANSION: clauses extending reach beyond what users expect.\n"
            "   - cross_entity: agreeing to one service binds you to terms of subsidiaries/affiliates.\n"
            "   - survival_clause: obligations surviving termination.\n"
            "   - unilateral_modification: company can change terms without explicit consent.\n"
            "   - binding_heirs: terms binding user's estate or heirs.\n"
            "   - physical_world: digital terms affecting physical-world rights (medical, biometric, property).\n"
            "5. INDEMNIFICATION: what the user is personally liable for.\n"
            "6. TERMINATION CONSEQUENCES: what happens to data, content, and access on termination.\n"
            "7. DANGERS: material risks, one-sided legal terms, or meaningful trade-offs **stated in the chunk**.\n"
            "   Skip routine signup or category-norm requirements (e.g. phone for messaging, email for accounts)\n"
            "   unless the text ties them to unusual extra processing, sharing, or retention worth flagging.\n"
            "   Goal: help users prioritize — not list every basic requirement as a red flag.\n"
            "8. BENEFITS: protections and user-friendly practices the document actually claims.\n"
            "9. RECOMMENDED ACTIONS: practical steps a user can take (settings, reading linked policies, opt-outs)\n"
            "   with specific URLs or instructions when present — helpful tone, not alarmist."
        ),
    )


_build_cluster_specs()

CLUSTER_NAMES = ["data_practices", "sharing_transfers", "rights_ai", "legal_scope"]


def _get_extraction_prompt(document: Document, chunk: str, cluster: str) -> str:
    schema_hint, notes = _CLUSTER_SPECS[cluster]

    header = f"""\
Extract evidence-backed facts from this policy document chunk.

Document URL: {document.url}
Document Type: {document.doc_type}

Text chunk:
{chunk}

Return a JSON object with ONLY the keys listed below (all keys required).
Evidence quotes must be EXACT substrings of the chunk above.
"""
    return f"{header}\n{json.dumps(schema_hint, separators=(',', ':'))}\n\nNotes:\n{notes}"


# ---------------------------------------------------------------------------
# Synonym normalisation
# ---------------------------------------------------------------------------

_SYNONYM_MAP: dict[str, str] = {
    "e-mail": "email",
    "e-mail address": "email address",
    "ip-address": "ip address",
    "phone number": "phone number",
    "telephone number": "phone number",
    "mobile number": "phone number",
    "date of birth": "date of birth",
    "birth date": "date of birth",
    "geolocation": "location",
    "geo-location": "location",
    "gps location": "location",
    "precise location": "location",
    "full name": "name",
    "first name": "name",
    "last name": "name",
    "user name": "username",
    "biometric data": "biometrics",
    "biometric information": "biometrics",
    "facial recognition data": "biometrics",
    "health data": "health information",
    "medical information": "health information",
    "genetic data": "genetic information",
    "financial information": "financial data",
    "payment information": "payment data",
    "credit card": "payment data",
}


def _dedupe_key(value: str) -> str:
    normalized = re.sub(r"\s+", " ", (value or "")).strip().lower()
    return _SYNONYM_MAP.get(normalized, normalized)


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def _merge_text_items(
    existing: dict[str, ExtractedTextItem],
    items: list[_Item],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.value)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedTextItem(value=item.value.strip(), evidence=[])
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_data_items(
    existing: dict[str, ExtractedDataItem],
    items: list[_DataItem],
    *,
    document: Document,
    content_hash: str,
) -> None:
    sensitivity_order = {"low": 0, "medium": 1, "high": 2, "sensitive": 3}
    for item in items:
        key = _dedupe_key(item.data_type)
        if not key:
            continue
        sens = item.sensitivity.strip().lower() if item.sensitivity else "medium"
        if sens not in sensitivity_order:
            sens = "medium"
        req = item.required.strip().lower() if item.required else "unclear"
        if req not in {"required", "optional", "unclear"}:
            req = "unclear"
        if key not in existing:
            existing[key] = ExtractedDataItem(
                data_type=item.data_type.strip(),
                sensitivity=cast(Any, sens),
                required=cast(Any, req),
                evidence=[],
            )
        else:
            cur_sens = sensitivity_order.get(existing[key].sensitivity, 1)
            new_sens = sensitivity_order.get(sens, 1)
            if new_sens > cur_sens:
                existing[key].sensitivity = cast(Any, sens)
            if req == "required":
                existing[key].required = "required"
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_purpose_links(
    existing: dict[str, ExtractedDataPurposeLink],
    items: list[_PurposeLink],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.data_type)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedDataPurposeLink(
                data_type=item.data_type.strip(), purposes=[], evidence=[]
            )
        for p in item.purposes or []:
            p_norm = re.sub(r"\s+", " ", p).strip()
            if p_norm and p_norm not in existing[key].purposes:
                existing[key].purposes.append(p_norm)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_retention_rules(
    existing: dict[str, ExtractedRetentionRule],
    items: list[_RetentionRule],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.data_scope)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedRetentionRule(
                data_scope=item.data_scope.strip(),
                duration=item.duration.strip() if item.duration else "Not specified",
                conditions=item.conditions.strip() if item.conditions else None,
                evidence=[],
            )
        else:
            if item.duration and len(item.duration) > len(existing[key].duration):
                existing[key].duration = item.duration.strip()
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_cookie_trackers(
    existing: dict[str, ExtractedCookieTracker],
    items: list[_CookieTracker],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_categories = {"essential", "analytics", "advertising", "social", "other"}
    for item in items:
        key = _dedupe_key(item.name_or_type)
        if not key:
            continue
        cat = item.category.strip().lower() if item.category else "other"
        if cat not in valid_categories:
            cat = "other"
        if key not in existing:
            existing[key] = ExtractedCookieTracker(
                name_or_type=item.name_or_type.strip(),
                category=cast(Any, cat),
                duration=item.duration.strip() if item.duration else None,
                third_party=item.third_party,
                opt_out_mechanism=item.opt_out_mechanism.strip()
                if item.opt_out_mechanism
                else None,
                evidence=[],
            )
        else:
            if item.third_party:
                existing[key].third_party = True
            if item.opt_out_mechanism and not existing[key].opt_out_mechanism:
                existing[key].opt_out_mechanism = item.opt_out_mechanism.strip()
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_third_parties(
    existing: dict[str, ExtractedThirdPartyRecipient],
    items: list[_ThirdParty],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.recipient)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedThirdPartyRecipient(
                recipient=item.recipient.strip(),
                data_shared=[],
                purpose=item.purpose.strip() if item.purpose else None,
                risk_level="medium",
                evidence=[],
            )
        for d in item.data_shared or []:
            d_norm = re.sub(r"\s+", " ", d).strip()
            if d_norm and d_norm not in existing[key].data_shared:
                existing[key].data_shared.append(d_norm)
        if item.purpose:
            new_purpose = item.purpose.strip()
            cur_purpose = existing[key].purpose
            if not cur_purpose or len(new_purpose) > len(cur_purpose):
                existing[key].purpose = new_purpose
        if item.risk_level:
            rl = item.risk_level.strip().lower()
            if rl in {"low", "medium", "high"}:
                existing[key].risk_level = cast(Any, rl)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_international_transfers(
    existing: dict[str, ExtractedInternationalTransfer],
    items: list[_InternationalTransfer],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.destination)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedInternationalTransfer(
                destination=item.destination.strip(),
                mechanism=item.mechanism.strip() if item.mechanism else None,
                data_types=[],
                evidence=[],
            )
        for dt in item.data_types or []:
            dt_norm = re.sub(r"\s+", " ", dt).strip()
            if dt_norm and dt_norm not in existing[key].data_types:
                existing[key].data_types.append(dt_norm)
        if item.mechanism and not existing[key].mechanism:
            existing[key].mechanism = item.mechanism.strip()
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_government_access(
    existing: dict[str, ExtractedGovernmentAccess],
    items: list[_GovernmentAccess],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(f"{item.authority_type}:{item.conditions}")
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedGovernmentAccess(
                authority_type=item.authority_type.strip(),
                conditions=item.conditions.strip(),
                data_scope=item.data_scope.strip() if item.data_scope else None,
                evidence=[],
            )
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_corporate_family(
    existing: dict[str, ExtractedCorporateFamilySharing],
    items: list[_CorporateFamily],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        ent_key = _dedupe_key(
            ",".join(sorted(item.entities)) if item.entities else item.purpose or "unnamed"
        )
        if not ent_key:
            continue
        if ent_key not in existing:
            existing[ent_key] = ExtractedCorporateFamilySharing(
                entities=[e.strip() for e in item.entities],
                data_shared=[],
                purpose=item.purpose.strip() if item.purpose else None,
                evidence=[],
            )
        for d in item.data_shared or []:
            d_norm = re.sub(r"\s+", " ", d).strip()
            if d_norm and d_norm not in existing[ent_key].data_shared:
                existing[ent_key].data_shared.append(d_norm)
        if item.quote:
            existing[ent_key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_user_rights(
    existing: dict[str, ExtractedUserRight],
    items: list[_UserRight],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        key = _dedupe_key(item.right_type)
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedUserRight(
                right_type=item.right_type.strip(),
                description=item.description.strip(),
                mechanism=item.mechanism.strip() if item.mechanism else None,
                evidence=[],
            )
        else:
            if item.mechanism and not existing[key].mechanism:
                existing[key].mechanism = item.mechanism.strip()
            if item.description and len(item.description) > len(existing[key].description):
                existing[key].description = item.description.strip()
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_ai_usage(
    existing: dict[str, ExtractedAIUsage],
    items: list[_AIUsage],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_types = {
        "training_on_user_data",
        "automated_decisions",
        "profiling",
        "content_generation",
        "recommendation",
        "moderation",
        "other",
    }
    for item in items:
        ut = item.usage_type.strip().lower() if item.usage_type else "other"
        if ut not in valid_types:
            ut = "other"
        key = f"{ut}:{_dedupe_key(item.description)}"
        if not key:
            continue
        opt = item.opt_out_available.strip().lower() if item.opt_out_available else "unclear"
        if opt not in {"yes", "no", "unclear"}:
            opt = "unclear"
        if key not in existing:
            existing[key] = ExtractedAIUsage(
                usage_type=cast(Any, ut),
                description=item.description.strip(),
                data_involved=[],
                opt_out_available=cast(Any, opt),
                opt_out_mechanism=item.opt_out_mechanism.strip()
                if item.opt_out_mechanism
                else None,
                consequences=item.consequences.strip() if item.consequences else None,
                evidence=[],
            )
        else:
            if opt == "yes":
                existing[key].opt_out_available = "yes"
            if item.opt_out_mechanism and not existing[key].opt_out_mechanism:
                existing[key].opt_out_mechanism = item.opt_out_mechanism.strip()
        for di in item.data_involved or []:
            di_norm = re.sub(r"\s+", " ", di).strip()
            if di_norm and di_norm not in existing[key].data_involved:
                existing[key].data_involved.append(di_norm)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_children_policy(
    accumulated: ExtractedChildrenPolicy | None,
    chunk_policy: _ChildrenPolicy | None,
    *,
    document: Document,
    content_hash: str,
) -> ExtractedChildrenPolicy | None:
    if not chunk_policy or (not chunk_policy.quote and chunk_policy.minimum_age is None):
        return accumulated
    if accumulated is None:
        accumulated = ExtractedChildrenPolicy(evidence=[])
    if chunk_policy.minimum_age is not None:
        if accumulated.minimum_age is None or chunk_policy.minimum_age > accumulated.minimum_age:
            accumulated.minimum_age = chunk_policy.minimum_age
    if chunk_policy.parental_consent_required:
        accumulated.parental_consent_required = True
    if chunk_policy.special_protections:
        sp = chunk_policy.special_protections.strip()
        if not accumulated.special_protections or len(sp) > len(accumulated.special_protections):
            accumulated.special_protections = sp
    if chunk_policy.quote:
        accumulated.evidence.append(_make_evidence(document, content_hash, chunk_policy.quote))
    return accumulated


def _merge_liability(
    existing: dict[str, ExtractedLiability],
    items: list[_Liability],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_types = {"cap", "waiver", "exclusion", "indemnification"}
    for item in items:
        lt = item.limitation_type.strip().lower() if item.limitation_type else "waiver"
        if lt not in valid_types:
            lt = "waiver"
        key = f"{lt}:{_dedupe_key(item.scope)}"
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedLiability(
                scope=item.scope.strip(),
                limitation_type=cast(Any, lt),
                description=item.description.strip(),
                extends_beyond_product=item.extends_beyond_product,
                evidence=[],
            )
        else:
            if item.extends_beyond_product:
                existing[key].extends_beyond_product = True
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_dispute_resolution(
    existing: dict[str, ExtractedDisputeResolution],
    items: list[_DisputeResolution],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_mechanisms = {"arbitration", "litigation", "mediation", "other"}
    for item in items:
        mech = item.mechanism.strip().lower() if item.mechanism else "other"
        if mech not in valid_mechanisms:
            mech = "other"
        key = f"{mech}:{_dedupe_key(item.venue or '')}:{_dedupe_key(item.governing_law or '')}"
        if key not in existing:
            existing[key] = ExtractedDisputeResolution(
                mechanism=cast(Any, mech),
                class_action_waiver=item.class_action_waiver,
                jury_trial_waiver=item.jury_trial_waiver,
                venue=item.venue.strip() if item.venue else None,
                governing_law=item.governing_law.strip() if item.governing_law else None,
                description=item.description.strip() if item.description else None,
                evidence=[],
            )
        else:
            if item.class_action_waiver:
                existing[key].class_action_waiver = True
            if item.jury_trial_waiver:
                existing[key].jury_trial_waiver = True
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_content_ownership(
    existing: dict[str, ExtractedContentOwnership],
    items: list[_ContentOwnership],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_types = {
        "license_to_company",
        "user_retains",
        "company_owns",
        "ai_training_rights",
        "likeness_rights",
        "other",
    }
    for item in items:
        ot = item.ownership_type.strip().lower() if item.ownership_type else "other"
        if ot not in valid_types:
            ot = "other"
        key = f"{ot}:{_dedupe_key(item.scope)}"
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedContentOwnership(
                ownership_type=cast(Any, ot),
                scope=item.scope.strip(),
                description=item.description.strip(),
                evidence=[],
            )
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_scope_expansion(
    existing: dict[str, ExtractedScopeExpansion],
    items: list[_ScopeExpansion],
    *,
    document: Document,
    content_hash: str,
) -> None:
    valid_types = {
        "cross_entity",
        "survival_clause",
        "unilateral_modification",
        "binding_heirs",
        "physical_world",
        "other",
    }
    for item in items:
        st = item.scope_type.strip().lower() if item.scope_type else "other"
        if st not in valid_types:
            st = "other"
        key = f"{st}:{_dedupe_key(item.description)}"
        if not key:
            continue
        if key not in existing:
            existing[key] = ExtractedScopeExpansion(
                scope_type=cast(Any, st),
                description=item.description.strip(),
                entities_affected=[e.strip() for e in item.entities_affected],
                evidence=[],
            )
        else:
            for e in item.entities_affected:
                e_norm = e.strip()
                if e_norm and e_norm not in existing[key].entities_affected:
                    existing[key].entities_affected.append(e_norm)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_privacy_signals(
    accumulated: PrivacySignals,
    chunk_signals: _PrivacySignals | None,
    *,
    document: Document | None = None,
    content_hash: str = "",
) -> None:
    if not chunk_signals:
        return

    def _add_evidence(quote: str | None) -> None:
        if quote and document:
            accumulated.evidence.append(_make_evidence(document, content_hash, quote))

    def _merge_yes_no(current: str, new_val: str | None, quote_field: str | None) -> str:
        """For yes/no/unclear signals: yes > no > unclear."""
        if not new_val:
            return current
        val = new_val.strip().lower()
        if val == "yes":
            _add_evidence(quote_field)
            return "yes"
        elif val == "no" and current == "unclear":
            _add_evidence(quote_field)
            return "no"
        return current

    accumulated.sells_data = cast(
        Any,
        _merge_yes_no(
            accumulated.sells_data, chunk_signals.sells_data, chunk_signals.sells_data_quote
        ),
    )
    accumulated.cross_site_tracking = cast(
        Any,
        _merge_yes_no(
            accumulated.cross_site_tracking,
            chunk_signals.cross_site_tracking,
            chunk_signals.cross_site_tracking_quote,
        ),
    )
    accumulated.ai_training_on_user_data = cast(
        Any,
        _merge_yes_no(
            accumulated.ai_training_on_user_data,
            chunk_signals.ai_training_on_user_data,
            chunk_signals.ai_training_quote,
        ),
    )
    accumulated.data_minimization = cast(
        Any,
        _merge_yes_no(
            accumulated.data_minimization,
            chunk_signals.data_minimization,
            chunk_signals.data_minimization_quote,
        ),
    )

    # account_deletion: self_service > request_required > not_specified
    if chunk_signals.account_deletion:
        val = chunk_signals.account_deletion.strip().lower()
        if val == "self_service":
            accumulated.account_deletion = "self_service"
            _add_evidence(chunk_signals.account_deletion_quote)
        elif val == "request_required" and accumulated.account_deletion == "not_specified":
            accumulated.account_deletion = "request_required"
            _add_evidence(chunk_signals.account_deletion_quote)

    # data_retention_summary: keep longer/more informative value
    if chunk_signals.data_retention_summary:
        new_val = chunk_signals.data_retention_summary.strip()
        if not accumulated.data_retention_summary or len(new_val) > len(
            accumulated.data_retention_summary
        ):
            accumulated.data_retention_summary = new_val
            _add_evidence(chunk_signals.data_retention_quote)

    # consent_model: opt_in/opt_out > mixed > not_specified
    if chunk_signals.consent_model:
        val = chunk_signals.consent_model.strip().lower()
        if val in ("opt_in", "opt_out"):
            if accumulated.consent_model == "not_specified":
                accumulated.consent_model = cast(Any, val)
                _add_evidence(chunk_signals.consent_model_quote)
            elif (
                accumulated.consent_model in ("opt_in", "opt_out")
                and accumulated.consent_model != val
            ):
                accumulated.consent_model = "mixed"
                _add_evidence(chunk_signals.consent_model_quote)
        elif val == "mixed":
            accumulated.consent_model = "mixed"
            _add_evidence(chunk_signals.consent_model_quote)

    # breach_notification: yes > no > not_specified
    if chunk_signals.breach_notification:
        val = chunk_signals.breach_notification.strip().lower()
        if val == "yes":
            accumulated.breach_notification = "yes"
            _add_evidence(chunk_signals.breach_notification_quote)
        elif val == "no" and accumulated.breach_notification == "not_specified":
            accumulated.breach_notification = "no"
            _add_evidence(chunk_signals.breach_notification_quote)

    # children_data_collection: yes > no > not_specified
    if chunk_signals.children_data_collection:
        val = chunk_signals.children_data_collection.strip().lower()
        if val == "yes":
            accumulated.children_data_collection = "yes"
            _add_evidence(chunk_signals.children_data_collection_quote)
        elif val == "no" and accumulated.children_data_collection == "not_specified":
            accumulated.children_data_collection = "no"
            _add_evidence(chunk_signals.children_data_collection_quote)


# ---------------------------------------------------------------------------
# Raw response cleaning
# ---------------------------------------------------------------------------


def _clean_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise common LLM response quirks before Pydantic validation."""
    if not isinstance(raw, dict):
        return raw
    for _key, val in raw.items():
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    for k, v in item.items():
                        if v is not None and not isinstance(
                            v, str | bool | int | float | list | dict
                        ):
                            item[k] = str(v)
    return raw


# ---------------------------------------------------------------------------
# Main extraction entry-point
# ---------------------------------------------------------------------------


async def extract_document_facts(
    document: Document,
    *,
    use_cache: bool = True,
    cancellation_token: CancellationToken | None = None,
) -> DocumentExtraction:
    """Extract evidence-backed facts from a document.

    For each semantic chunk we launch **four clustered LLM calls in parallel**:
      1. data_practices: data collected, purposes, retention, security, cookies
      2. sharing_transfers: third-party sharing, international, government, corporate family
      3. rights_ai: user rights, consent, account lifecycle, AI/profiling, children
      4. legal_scope: liability, disputes, content ownership, scope, indemnification, termination
    """
    token = cancellation_token or CancellationToken()
    logger.debug(f"Starting v4 extraction for document {document.id} (use_cache={use_cache})")

    content_hash = (
        document.metadata.get("content_hash") if document.metadata else None
    ) or _compute_content_hash(document)

    if (
        use_cache
        and document.extraction
        and document.extraction.source_content_hash == content_hash
        and document.extraction.version == "v4"
    ):
        logger.debug(f"Using cached v4 extraction for document {document.id}")
        return document.extraction

    text = document.text or ""
    chunks = _chunk_text(text, chunk_size=8000, overlap=800)
    logger.debug(f"Chunked document {document.id} into {len(chunks)} chunk(s)")

    if not chunks:
        extraction = DocumentExtraction(
            version="v4",
            generated_at=datetime.now(),
            source_content_hash=content_hash,
        )
        document.extraction = extraction
        return extraction

    # Accumulation maps
    data_collected: dict[str, ExtractedDataItem] = {}
    data_purposes: dict[str, ExtractedDataPurposeLink] = {}
    retention_policies: dict[str, ExtractedRetentionRule] = {}
    security_measures: dict[str, ExtractedTextItem] = {}
    cookies_and_trackers: dict[str, ExtractedCookieTracker] = {}

    third_party_details: dict[str, ExtractedThirdPartyRecipient] = {}
    international_transfers: dict[str, ExtractedInternationalTransfer] = {}
    government_access: dict[str, ExtractedGovernmentAccess] = {}
    corporate_family_sharing: dict[str, ExtractedCorporateFamilySharing] = {}

    user_rights: dict[str, ExtractedUserRight] = {}
    consent_mechanisms: dict[str, ExtractedTextItem] = {}
    account_lifecycle: dict[str, ExtractedTextItem] = {}
    ai_usage: dict[str, ExtractedAIUsage] = {}
    children_policy: ExtractedChildrenPolicy | None = None

    liability: dict[str, ExtractedLiability] = {}
    dispute_resolution: dict[str, ExtractedDisputeResolution] = {}
    content_ownership: dict[str, ExtractedContentOwnership] = {}
    scope_expansion: dict[str, ExtractedScopeExpansion] = {}
    indemnification: dict[str, ExtractedTextItem] = {}
    termination_consequences: dict[str, ExtractedTextItem] = {}
    dangers: dict[str, ExtractedTextItem] = {}
    benefits: dict[str, ExtractedTextItem] = {}
    recommended_actions: dict[str, ExtractedTextItem] = {}

    accumulated_signals = PrivacySignals()

    _is_complex = (
        len(document.text or "") > _COMPLEX_DOC_LENGTH_THRESHOLD
        or document.doc_type in _COMPLEX_DOC_TYPES
    )

    async def _run_cluster(cluster_name: str, chunk_text: str, chunk_idx: int) -> dict[str, Any]:
        logger.debug(
            f"Running cluster '{cluster_name}' for {document.id} chunk {chunk_idx}/{len(chunks)}"
        )
        is_complex = _is_complex
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _get_extraction_prompt(document, chunk_text, cluster_name),
            },
        ]
        if is_complex:
            # Complex docs go straight to the escalation model. No validation step:
            # there is no higher-tier model to escalate to, so we accept the response.
            response = await acompletion_with_fallback(
                messages,
                model_priority=_EXTRACTION_ESCALATION,
                response_format={"type": "json_object"},
            )
        else:
            response = await acompletion_with_escalation(
                messages=messages,
                primary=_EXTRACTION_PRIMARY,
                escalation=_EXTRACTION_ESCALATION,
                validator=_extraction_validator(cluster_name),
                response_format={"type": "json_object"},
            )
        logger.info(
            "Cluster '%s' for %s chunk %d completed with model %s",
            cluster_name,
            document.id,
            chunk_idx,
            response.model,
        )
        choice = response.choices[0]
        if not hasattr(choice, "message"):
            raise ValueError("Unexpected response format: missing message attribute")
        message = choice.message  # type: ignore[attr-defined]
        if not message:
            raise ValueError("Unexpected response format: message is None")
        content = message.content  # type: ignore[attr-defined]
        if not content:
            raise ValueError("Empty response from LLM")
        return json.loads(content)

    chunk_semaphore = asyncio.Semaphore(5)
    merge_lock = asyncio.Lock()

    async def _process_chunk(idx: int, chunk: str) -> None:
        await token.check_cancellation()
        async with chunk_semaphore:
            logger.debug(
                f"Extracting v4 facts for {document.id}: chunk {idx}/{len(chunks)} (4 parallel clusters)"
            )

            results = await asyncio.gather(
                *(_run_cluster(name, chunk, idx) for name in CLUSTER_NAMES),
                return_exceptions=True,
            )

        safe: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    f"Cluster '{CLUSTER_NAMES[i]}' failed for {document.id} chunk {idx}: {result}"
                )
                safe.append({})
            else:
                safe.append(_clean_raw(result))

        dp_raw, st_raw, ra_raw, ls_raw = safe

        try:
            dp = _ClusterDataPractices.model_validate(dp_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for data_practices chunk {idx}: {e}")
            dp = _ClusterDataPractices()
        try:
            st = _ClusterSharingTransfers.model_validate(st_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for sharing_transfers chunk {idx}: {e}")
            st = _ClusterSharingTransfers()
        try:
            ra = _ClusterRightsAI.model_validate(ra_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for rights_ai chunk {idx}: {e}")
            ra = _ClusterRightsAI()
        try:
            ls = _ClusterLegalScope.model_validate(ls_raw, strict=False)
        except Exception as e:
            logger.warning(f"Validation failed for legal_scope chunk {idx}: {e}")
            ls = _ClusterLegalScope()

        nonlocal children_policy

        async with merge_lock:
            # Cluster 1
            _merge_data_items(
                data_collected, dp.data_collected, document=document, content_hash=content_hash
            )
            _merge_purpose_links(
                data_purposes, dp.data_purposes, document=document, content_hash=content_hash
            )
            _merge_retention_rules(
                retention_policies,
                dp.retention_policies,
                document=document,
                content_hash=content_hash,
            )
            _merge_text_items(
                security_measures,
                dp.security_measures,
                document=document,
                content_hash=content_hash,
            )
            _merge_cookie_trackers(
                cookies_and_trackers,
                dp.cookies_and_trackers,
                document=document,
                content_hash=content_hash,
            )

            # Cluster 2
            _merge_third_parties(
                third_party_details,
                st.third_party_details,
                document=document,
                content_hash=content_hash,
            )
            _merge_international_transfers(
                international_transfers,
                st.international_transfers,
                document=document,
                content_hash=content_hash,
            )
            _merge_government_access(
                government_access,
                st.government_access,
                document=document,
                content_hash=content_hash,
            )
            _merge_corporate_family(
                corporate_family_sharing,
                st.corporate_family_sharing,
                document=document,
                content_hash=content_hash,
            )

            # Cluster 3
            _merge_user_rights(
                user_rights, ra.user_rights, document=document, content_hash=content_hash
            )
            _merge_text_items(
                consent_mechanisms,
                ra.consent_mechanisms,
                document=document,
                content_hash=content_hash,
            )
            _merge_text_items(
                account_lifecycle,
                ra.account_lifecycle,
                document=document,
                content_hash=content_hash,
            )
            _merge_ai_usage(ai_usage, ra.ai_usage, document=document, content_hash=content_hash)
            children_policy = _merge_children_policy(
                children_policy, ra.children_policy, document=document, content_hash=content_hash
            )
            _merge_privacy_signals(
                accumulated_signals,
                ra.privacy_signals,
                document=document,
                content_hash=content_hash,
            )

            # Cluster 4
            _merge_liability(liability, ls.liability, document=document, content_hash=content_hash)
            _merge_dispute_resolution(
                dispute_resolution,
                ls.dispute_resolution,
                document=document,
                content_hash=content_hash,
            )
            _merge_content_ownership(
                content_ownership,
                ls.content_ownership,
                document=document,
                content_hash=content_hash,
            )
            _merge_scope_expansion(
                scope_expansion, ls.scope_expansion, document=document, content_hash=content_hash
            )
            _merge_text_items(
                indemnification, ls.indemnification, document=document, content_hash=content_hash
            )
            _merge_text_items(
                termination_consequences,
                ls.termination_consequences,
                document=document,
                content_hash=content_hash,
            )
            _merge_text_items(dangers, ls.dangers, document=document, content_hash=content_hash)
            _merge_text_items(benefits, ls.benefits, document=document, content_hash=content_hash)
            _merge_text_items(
                recommended_actions,
                ls.recommended_actions,
                document=document,
                content_hash=content_hash,
            )

    chunk_results = await asyncio.gather(
        *(_process_chunk(idx, chunk) for idx, chunk in enumerate(chunks, 1)),
        return_exceptions=True,
    )
    failed_chunks = 0
    for i, result in enumerate(chunk_results):
        if isinstance(result, BaseException):
            failed_chunks += 1
            logger.warning(f"Chunk {i + 1}/{len(chunks)} failed for {document.id}: {result}")
    if failed_chunks:
        logger.warning(f"{failed_chunks}/{len(chunks)} chunks failed for {document.id}")

    extraction = DocumentExtraction(
        version="v4",
        generated_at=datetime.now(),
        source_content_hash=content_hash,
        # Cluster 1
        data_collected=list(data_collected.values()),
        data_purposes=list(data_purposes.values()),
        retention_policies=list(retention_policies.values()),
        security_measures=list(security_measures.values()),
        cookies_and_trackers=list(cookies_and_trackers.values()),
        # Cluster 2
        third_party_details=list(third_party_details.values()),
        international_transfers=list(international_transfers.values()),
        government_access=list(government_access.values()),
        corporate_family_sharing=list(corporate_family_sharing.values()),
        # Cluster 3
        user_rights=list(user_rights.values()),
        consent_mechanisms=list(consent_mechanisms.values()),
        account_lifecycle=list(account_lifecycle.values()),
        ai_usage=list(ai_usage.values()),
        children_policy=children_policy,
        # Cluster 4
        liability=list(liability.values()),
        dispute_resolution=list(dispute_resolution.values()),
        content_ownership=list(content_ownership.values()),
        scope_expansion=list(scope_expansion.values()),
        indemnification=list(indemnification.values()),
        termination_consequences=list(termination_consequences.values()),
        # Cross-cutting
        privacy_signals=accumulated_signals,
        dangers=list(dangers.values()),
        benefits=list(benefits.values()),
        recommended_actions=list(recommended_actions.values()),
    )

    logger.debug(
        f"v4 extraction complete for {document.id}: "
        f"data={len(extraction.data_collected)}, rights={len(extraction.user_rights)}, "
        f"ai={len(extraction.ai_usage)}, liability={len(extraction.liability)}, "
        f"scope_expansion={len(extraction.scope_expansion)}, "
        f"content_ownership={len(extraction.content_ownership)}"
    )

    document.extraction = extraction
    document.metadata["extraction_version"] = extraction.version
    document.metadata["extraction_generated_at"] = extraction.generated_at.isoformat()
    document.metadata["extraction_source_hash"] = content_hash

    return extraction
