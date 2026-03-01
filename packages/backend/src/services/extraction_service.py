"""Evidence-first extraction for legal documents.

This service extracts structured facts from a document WITH evidence (exact quotes),
so downstream summaries can be generated from extracted facts only.

Clusters (per chunk, all run in parallel):
  Cluster 1 - Data & Storage:    data_collected, data_purposes, data_collection_details,
                                  retention_policy, security_measures
  Cluster 2 - Sharing & Rights:  third_party_details, your_rights, contract_clauses
  Cluster 3 - Risk & Signals:    dangers, benefits, recommended_actions, privacy_signals,
                                  advertising_practices, profiling_ai

3 parallel calls per chunk — total latency ≈ one serial call.
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
from src.llm import SupportedModel, acompletion_with_fallback
from src.models.document import (
    ContractClauseType,
    Document,
    DocumentExtraction,
    EvidenceSpan,
    ExtractedContractClause,
    ExtractedDataPurposeLink,
    ExtractedTextItem,
    ExtractedThirdPartyRecipient,
    PrivacySignals,
)
from src.utils.cancellation import CancellationToken

logger = get_logger(__name__)


def _compute_content_hash(document: Document) -> str:
    """Keep hashing consistent with summarizer caching (text + doc_type)."""
    content = f"{document.text}{document.doc_type}"
    return hashlib.sha256(content.encode()).hexdigest()


def _chunk_text(text: str, *, chunk_size: int = 8000, overlap: int = 800) -> list[str]:
    """Split *text* into chunks, respecting Markdown section boundaries.

    Strategy:
    1. Split on Markdown headers (``#`` … ``######``).
    2. Accumulate sections into chunks that stay under *chunk_size*.
    3. If a single section is too long, fall back to character-level splitting
       with *overlap* so context is preserved across boundaries.

    This preserves legal clause context far better than blind character splits.
    """
    if not text:
        return []
    if chunk_size <= 0:
        return [text]
    overlap = max(0, min(overlap, chunk_size - 1))

    # Split on header lines while keeping the header as the start of each part.
    parts = re.split(r"(?m)^(#{1,6}\s+.*)", text)

    # Reconstruct (header + body) sections
    sections: list[str] = []
    # The first element is content before any header
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

    # For sections that exceed chunk_size, do character-level splitting with overlap.
    final_chunks: list[str] = []
    for section in sections:
        if len(section) <= chunk_size:
            final_chunks.append(section)
            continue
        start = 0
        n = len(section)
        while start < n:
            end = min(n, start + chunk_size)
            final_chunks.append(section[start:end])
            if end >= n:
                break
            start = max(0, end - overlap)

    return final_chunks


def _resolve_quote_offsets(haystack: str, quote: str) -> tuple[int | None, int | None]:
    """Best-effort locate quote in the original text.

    We prefer exact substring match. If that fails, we attempt a whitespace-collapsed match
    (offsets will be unavailable in that case because mapping indices is non-trivial).
    """
    if not haystack or not quote:
        return None, None
    idx = haystack.find(quote)
    if idx != -1:
        return idx, idx + len(quote)

    # Fallback: try a looser match to validate presence; do not return offsets.
    def _collapse_ws(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    collapsed_h = _collapse_ws(haystack)
    collapsed_q = _collapse_ws(quote)
    if collapsed_q and collapsed_q in collapsed_h:
        return None, None

    return None, None


def _make_evidence(document: Document, content_hash: str, quote: str) -> EvidenceSpan:
    start_char, end_char = _resolve_quote_offsets(document.text, quote)
    return EvidenceSpan(
        document_id=document.id,
        url=document.url,
        content_hash=content_hash,
        quote=quote,
        start_char=start_char,
        end_char=end_char,
        section_title=None,
    )


# ---------------------------------------------------------------------------
# Pydantic models for each specialized extraction pipeline
# ---------------------------------------------------------------------------


class _ExtractionItem(BaseModel):
    value: str
    quote: str


class _ExtractionDataPurposeLink(BaseModel):
    data_type: str
    purposes: list[str] = Field(default_factory=list)
    quote: str


class _ExtractionThirdParty(BaseModel):
    recipient: str
    data_shared: list[str] = Field(default_factory=list)
    purpose: str | None = None
    risk_level: str | None = None
    quote: str


class _ExtractionPrivacySignals(BaseModel):
    """Privacy signals extracted from a single chunk."""

    sells_data: str | None = None  # "yes", "no", "unclear"
    cross_site_tracking: str | None = None  # "yes", "no", "unclear"
    account_deletion: str | None = None  # "self_service", "request_required", "not_specified"
    data_retention_summary: str | None = None  # e.g. "30 days", "indefinite"
    consent_model: str | None = None  # "opt_in", "opt_out", "mixed", "not_specified"


# Contract clause item (used by sharing_rights cluster)
class _ExtractionContractClause(BaseModel):
    clause_type: str
    value: str
    quote: str


# Cluster 1: Data & Storage (story + retention + security)
class _ClusterDataStorageResult(BaseModel):
    data_collected: list[_ExtractionItem] = Field(default_factory=list)
    data_purposes: list[_ExtractionItem] = Field(default_factory=list)
    data_collection_details: list[_ExtractionDataPurposeLink] = Field(default_factory=list)
    retention_policy: list[_ExtractionItem] = Field(default_factory=list)
    security_measures: list[_ExtractionItem] = Field(default_factory=list)


# Cluster 2: Sharing & Rights (sharing + rights + contract)
class _ClusterSharingRightsResult(BaseModel):
    third_party_details: list[_ExtractionThirdParty] = Field(default_factory=list)
    your_rights: list[_ExtractionItem] = Field(default_factory=list)
    contract_clauses: list[_ExtractionContractClause] = Field(default_factory=list)


# Cluster 3: Risk & Signals (risk + signals + advertising + profiling)
class _ClusterRiskSignalsResult(BaseModel):
    dangers: list[_ExtractionItem] = Field(default_factory=list)
    benefits: list[_ExtractionItem] = Field(default_factory=list)
    recommended_actions: list[_ExtractionItem] = Field(default_factory=list)
    privacy_signals: _ExtractionPrivacySignals | None = None
    advertising_practices: list[_ExtractionItem] = Field(default_factory=list)
    profiling_ai: list[_ExtractionItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are an expert legal-document information extractor.

Your job is to extract structured facts ONLY from the provided text chunk.

Critical rules:
- Only extract items explicitly present in the text chunk.
- For every extracted item, provide an evidence quote that is an EXACT substring of the provided chunk.
- If a field is not present, return an empty list for that field.
- Do not paraphrase evidence quotes; copy exact text.
"""


def _get_extraction_prompt(document: Document, chunk: str, cluster: str) -> str:
    """Return a focused user prompt for one of the three extraction clusters."""

    header = f"""\
Extract evidence-backed facts from this legal document chunk.

Document URL: {document.url}
Document Type: {document.doc_type}

Text chunk:
{chunk}

Return a JSON object with ONLY the keys listed below (all keys required).
Evidence quotes must be EXACT substrings of the chunk above.
"""

    if cluster == "data_storage":
        schema_hint = {
            "data_collected": [{"value": "Email address", "quote": "exact quote"}],
            "data_purposes": [{"value": "Personalized advertising", "quote": "exact quote"}],
            "data_collection_details": [
                {
                    "data_type": "Email address",
                    "purposes": ["Account creation", "Security"],
                    "quote": "exact quote",
                }
            ],
            "retention_policy": [
                {"value": "Account data retained 30 days after deletion", "quote": "exact quote"}
            ],
            "security_measures": [
                {"value": "Encryption in transit and at rest", "quote": "exact quote"}
            ],
        }
        notes = (
            "Extract ALL of the following from this chunk:\n"
            "1. WHAT data is collected and WHY (data_collected, data_purposes, data_collection_details).\n"
            "   Keep `value` short and normalized (deduplicate 'e-mail' vs 'email').\n"
            "2. Data RETENTION periods, deletion timelines, storage duration (retention_policy).\n"
            "3. SECURITY safeguards: encryption, access controls, audits, breach response (security_measures)."
        )

    elif cluster == "sharing_rights":
        schema_hint = {
            "third_party_details": [
                {
                    "recipient": "Advertisers",
                    "data_shared": ["email", "location data"],
                    "purpose": "Targeted advertising",
                    "risk_level": "high",
                    "quote": "exact quote",
                }
            ],
            "your_rights": [
                {"value": "Delete your account via Settings > Privacy", "quote": "exact quote"}
            ],
            "contract_clauses": [
                {
                    "clause_type": "arbitration | liability | governing_law | jurisdiction",
                    "value": "Disputes resolved by binding arbitration in California",
                    "quote": "exact quote",
                }
            ],
        }
        notes = (
            "Extract ALL of the following from this chunk:\n"
            "1. Third-party SHARING: who receives data, what data, why, risk level (low/medium/high).\n"
            "2. User RIGHTS: access, correction, deletion, portability. Include specific URLs or instructions.\n"
            "3. CONTRACT clauses: arbitration, governing law, jurisdiction, liability limitations.\n"
            "   Capture class action waivers, jury-trial waivers, mass arbitration rules, and venue/forum requirements\n"
            "   under arbitration. Capture liability waivers or caps under liability. Use clause_type values from the hint."
        )

    elif cluster == "risk_signals":
        schema_hint = {
            "dangers": [{"value": "No retention period specified", "quote": "exact quote"}],
            "benefits": [{"value": "Encryption in transit and at rest", "quote": "exact quote"}],
            "recommended_actions": [
                {"value": "Opt out of ads at example.com/privacy/ads", "quote": "exact quote"}
            ],
            "privacy_signals": {
                "sells_data": "yes | no | unclear  (null if not mentioned)",
                "cross_site_tracking": "yes | no | unclear  (null if not mentioned)",
                "account_deletion": "self_service | request_required | not_specified  (null if not mentioned)",
                "data_retention_summary": "e.g. '30 days' or 'indefinite'  (null if not mentioned)",
                "consent_model": "opt_in | opt_out | mixed | not_specified  (null if not mentioned)",
            },
            "advertising_practices": [
                {"value": "Targeted advertising with third-party partners", "quote": "exact quote"}
            ],
            "profiling_ai": [
                {
                    "value": "Automated profiling to personalize recommendations",
                    "quote": "exact quote",
                }
            ],
        }
        notes = (
            "Extract ALL of the following from this chunk:\n"
            "1. RISKS/dangers and positive BENEFITS/protections.\n"
            "   Flag explicit high-risk items like AI training/model improvement using user content or likeness,\n"
            "   broad content licenses (perpetual/irrevocable/sublicensable), biometric/health data use,\n"
            "   precise location tracking, cross-service/affiliate scope, unilateral changes, account termination,\n"
            "   and liability waivers for injury.\n"
            "2. RECOMMENDED ACTIONS: actionable steps with specific URLs or instructions.\n"
            "3. PRIVACY SIGNALS: only set a field if the chunk EXPLICITLY mentions it, null otherwise.\n"
            "   sells_data: selling/not selling personal data.\n"
            "   cross_site_tracking: cross-site/cross-device tracking, third-party ad cookies.\n"
            "   account_deletion: self-service (button/settings) vs contact-required.\n"
            "   data_retention_summary: specific periods ('30 days', '2 years', 'indefinite').\n"
            "   consent_model: opt-in (explicit agreement) vs opt-out (pre-selected).\n"
            "4. ADVERTISING practices, marketing, ad personalization. Include opt-out links if present.\n"
            "5. PROFILING/AI: automated decision-making, profiling, AI model training, or use of data to train AI."
        )

    else:
        raise ValueError(f"Unknown cluster: {cluster!r}")

    return f"{header}\n{json.dumps(schema_hint, indent=2)}\n\nNotes:\n{notes}"


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def _dedupe_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


def _clean_sharing_rights_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Clean raw LLM response for sharing rights cluster to handle validation issues."""
    if not isinstance(raw, dict):
        return raw

    # Clean third_party_details
    if "third_party_details" in raw and isinstance(raw["third_party_details"], list):
        for item in raw["third_party_details"]:
            if isinstance(item, dict) and "risk_level" in item:
                risk_level = item["risk_level"]
                # Convert empty list to None
                if risk_level == []:
                    item["risk_level"] = None
                # Ensure it's a string if it's not None
                elif risk_level is not None and not isinstance(risk_level, str):
                    item["risk_level"] = str(risk_level)

    return raw


def _merge_text_items(
    existing: dict[str, ExtractedTextItem],
    items: list[_ExtractionItem],
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


def _merge_data_purpose_links(
    existing: dict[str, ExtractedDataPurposeLink],
    items: list[_ExtractionDataPurposeLink],
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
                data_type=item.data_type.strip(),
                purposes=[],
                evidence=[],
            )
        # Merge purposes (dedupe)
        for p in item.purposes or []:
            p_norm = re.sub(r"\s+", " ", p).strip()
            if p_norm and p_norm not in existing[key].purposes:
                existing[key].purposes.append(p_norm)
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_third_parties(
    existing: dict[str, ExtractedThirdPartyRecipient],
    items: list[_ExtractionThirdParty],
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
        # Merge data_shared (dedupe)
        for d in item.data_shared or []:
            d_norm = re.sub(r"\s+", " ", d).strip()
            if d_norm and d_norm not in existing[key].data_shared:
                existing[key].data_shared.append(d_norm)
        # Merge purpose if missing
        if not existing[key].purpose and item.purpose:
            existing[key].purpose = item.purpose.strip()
        # Normalize risk_level if present
        if item.risk_level:
            rl = item.risk_level.strip().lower()
            if rl in {"low", "medium", "high"}:
                existing[key].risk_level = rl  # type: ignore[assignment]
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


def _merge_privacy_signals(
    accumulated: PrivacySignals,
    chunk_signals: _ExtractionPrivacySignals | None,
) -> None:
    """Merge privacy signals from a chunk into the accumulated result.

    Priority: explicit values ("yes"/"no") override "unclear"/"not_specified".
    "yes" takes precedence over "no" for sells_data and cross_site_tracking
    (if any chunk says data is sold, we flag it).
    """
    if not chunk_signals:
        return

    # sells_data: "yes" > "no" > "unclear"
    if chunk_signals.sells_data:
        val = chunk_signals.sells_data.strip().lower()
        if val == "yes":
            accumulated.sells_data = "yes"
        elif val == "no" and accumulated.sells_data == "unclear":
            accumulated.sells_data = "no"

    # cross_site_tracking: "yes" > "no" > "unclear"
    if chunk_signals.cross_site_tracking:
        val = chunk_signals.cross_site_tracking.strip().lower()
        if val == "yes":
            accumulated.cross_site_tracking = "yes"
        elif val == "no" and accumulated.cross_site_tracking == "unclear":
            accumulated.cross_site_tracking = "no"

    # account_deletion: "self_service" > "request_required" > "not_specified"
    if chunk_signals.account_deletion:
        val = chunk_signals.account_deletion.strip().lower()
        if val == "self_service":
            accumulated.account_deletion = "self_service"
        elif val == "request_required" and accumulated.account_deletion == "not_specified":
            accumulated.account_deletion = "request_required"

    # data_retention_summary: first non-null value wins, then longer/more specific overrides
    if chunk_signals.data_retention_summary and not accumulated.data_retention_summary:
        accumulated.data_retention_summary = chunk_signals.data_retention_summary.strip()

    # consent_model: "opt_in"/"opt_out" > "mixed" > "not_specified"
    if chunk_signals.consent_model:
        val = chunk_signals.consent_model.strip().lower()
        if val in ("opt_in", "opt_out"):
            if accumulated.consent_model == "not_specified":
                accumulated.consent_model = val  # type: ignore[assignment]
            elif (
                accumulated.consent_model in ("opt_in", "opt_out")
                and accumulated.consent_model != val
            ):
                accumulated.consent_model = "mixed"
        elif val == "mixed":
            accumulated.consent_model = "mixed"


def _merge_contract_clauses(
    existing: dict[str, ExtractedContractClause],
    items: list[_ExtractionContractClause],
    *,
    document: Document,
    content_hash: str,
) -> None:
    for item in items:
        clause_type = (item.clause_type or "").strip().lower()
        if clause_type not in {"liability", "arbitration", "governing_law", "jurisdiction"}:
            continue
        value = item.value.strip() if item.value else ""
        if not value:
            continue
        key = f"{clause_type}:{_dedupe_key(value)}"
        clause_type_literal = cast(ContractClauseType, clause_type)
        if key not in existing:
            existing[key] = ExtractedContractClause(
                clause_type=clause_type_literal, value=value, evidence=[]
            )
        if item.quote:
            existing[key].evidence.append(_make_evidence(document, content_hash, item.quote))


# ---------------------------------------------------------------------------
# Main extraction entry-point
# ---------------------------------------------------------------------------


async def extract_document_facts(
    document: Document,
    *,
    use_cache: bool = True,
    model_priority: list[SupportedModel] | None = None,
    cancellation_token: CancellationToken | None = None,
) -> DocumentExtraction:
    """Extract evidence-backed facts from a document.

    For each semantic chunk we launch **three clustered LLM calls in parallel**:
      1. data_storage: data collected, purposes, retention, security
      2. sharing_rights: third-party sharing, user rights, contract clauses
      3. risk_signals: risks, benefits, actions, privacy signals, ads, profiling

    Safe to call inside request handlers (supports cancellation), but may be slow
    depending on document length.
    """
    token = cancellation_token or CancellationToken()
    logger.debug(
        f"Starting extraction for document {document.id} "
        f"(use_cache={use_cache}, model_priority={model_priority})"
    )

    content_hash = (
        document.metadata.get("content_hash") if document.metadata else None
    ) or _compute_content_hash(document)

    if (
        use_cache
        and document.extraction
        and document.extraction.source_content_hash == content_hash
    ):
        logger.debug(
            f"Using cached extraction for document {document.id} (content_hash={content_hash})"
        )
        return document.extraction

    text = document.text or ""
    chunks = _chunk_text(text, chunk_size=8000, overlap=800)
    logger.debug(
        f"Chunked document {document.id} into {len(chunks)} chunk(s) (text_len={len(text)})"
    )
    if not chunks:
        logger.debug(f"No chunks found for document {document.id}; returning empty extraction")
        extraction = DocumentExtraction(
            version="v3",
            generated_at=datetime.now(),
            source_content_hash=content_hash,
        )
        document.extraction = extraction
        return extraction

    # Accumulation maps (deduplicated by normalised key)
    data_collected: dict[str, ExtractedTextItem] = {}
    data_purposes: dict[str, ExtractedTextItem] = {}
    your_rights: dict[str, ExtractedTextItem] = {}
    dangers: dict[str, ExtractedTextItem] = {}
    benefits: dict[str, ExtractedTextItem] = {}
    recommended_actions: dict[str, ExtractedTextItem] = {}
    data_collection_details: dict[str, ExtractedDataPurposeLink] = {}
    third_party_details: dict[str, ExtractedThirdPartyRecipient] = {}
    retention_policy: dict[str, ExtractedTextItem] = {}
    security_measures: dict[str, ExtractedTextItem] = {}
    advertising_practices: dict[str, ExtractedTextItem] = {}
    profiling_ai: dict[str, ExtractedTextItem] = {}
    contract_clauses: dict[str, ExtractedContractClause] = {}
    accumulated_signals = PrivacySignals()

    async def _run_pipeline(
        pipeline_name: str, chunk_text: str, chunk_index: int
    ) -> dict[str, Any]:
        """Run one specialised extraction pipeline against a chunk."""
        logger.debug(
            f"Running cluster '{pipeline_name}' for document {document.id} "
            f"chunk {chunk_index}/{len(chunks)}"
        )
        response = await acompletion_with_fallback(
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _get_extraction_prompt(document, chunk_text, pipeline_name),
                },
            ],
            model_priority=model_priority,
            response_format={"type": "json_object"},
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
        payload = json.loads(content)
        logger.debug(
            f"Cluster '{pipeline_name}' completed for document {document.id} "
            f"chunk {chunk_index}/{len(chunks)} (response_chars={len(content)})"
        )
        return payload

    for idx, chunk in enumerate(chunks, 1):
        await token.check_cancellation()
        logger.debug(
            f"Extracting facts for {document.id}: chunk {idx}/{len(chunks)} (3 parallel clusters)"
        )

        # Run 3 clustered pipelines concurrently for this chunk.
        cluster_names = ["data_storage", "sharing_rights", "risk_signals"]
        results = await asyncio.gather(
            *(_run_pipeline(name, chunk, idx) for name in cluster_names),
            return_exceptions=True,
        )

        # Replace failed clusters with empty dicts (Pydantic models use default_factory=list)
        safe_results: list[Any] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    f"Cluster '{cluster_names[i]}' failed for document {document.id} "
                    f"chunk {idx}: {result}"
                )
                safe_results.append({})
            else:
                safe_results.append(result)

        ds_raw, sr_raw, rs_raw = safe_results

        # Clean raw data to handle LLM inconsistencies
        sr_raw = _clean_sharing_rights_raw(sr_raw)

        ds = _ClusterDataStorageResult.model_validate(ds_raw, strict=False)
        sr = _ClusterSharingRightsResult.model_validate(sr_raw, strict=False)
        rs = _ClusterRiskSignalsResult.model_validate(rs_raw, strict=False)

        # Merge data_storage cluster
        _merge_text_items(
            data_collected, ds.data_collected, document=document, content_hash=content_hash
        )
        _merge_text_items(
            data_purposes, ds.data_purposes, document=document, content_hash=content_hash
        )
        _merge_data_purpose_links(
            data_collection_details,
            ds.data_collection_details,
            document=document,
            content_hash=content_hash,
        )
        _merge_text_items(
            retention_policy, ds.retention_policy, document=document, content_hash=content_hash
        )
        _merge_text_items(
            security_measures, ds.security_measures, document=document, content_hash=content_hash
        )

        # Merge sharing_rights cluster
        _merge_third_parties(
            third_party_details,
            sr.third_party_details,
            document=document,
            content_hash=content_hash,
        )
        _merge_text_items(your_rights, sr.your_rights, document=document, content_hash=content_hash)
        _merge_contract_clauses(
            contract_clauses,
            sr.contract_clauses,
            document=document,
            content_hash=content_hash,
        )

        # Merge risk_signals cluster
        _merge_text_items(dangers, rs.dangers, document=document, content_hash=content_hash)
        _merge_text_items(benefits, rs.benefits, document=document, content_hash=content_hash)
        _merge_text_items(
            recommended_actions,
            rs.recommended_actions,
            document=document,
            content_hash=content_hash,
        )
        _merge_privacy_signals(accumulated_signals, rs.privacy_signals)
        _merge_text_items(
            advertising_practices,
            rs.advertising_practices,
            document=document,
            content_hash=content_hash,
        )
        _merge_text_items(
            profiling_ai, rs.profiling_ai, document=document, content_hash=content_hash
        )
        logger.debug(
            f"Merged chunk {idx}/{len(chunks)} for document {document.id} "
            f"(data_collected={len(data_collected)}, data_purposes={len(data_purposes)}, "
            f"rights={len(your_rights)}, dangers={len(dangers)}, benefits={len(benefits)}, "
            f"actions={len(recommended_actions)}, third_parties={len(third_party_details)}, "
            f"contract_clauses={len(contract_clauses)})"
        )

    extraction = DocumentExtraction(
        version="v3",
        generated_at=datetime.now(),
        source_content_hash=content_hash,
        data_collected=list(data_collected.values()),
        data_purposes=list(data_purposes.values()),
        data_collection_details=list(data_collection_details.values()),
        third_party_details=list(third_party_details.values()),
        your_rights=list(your_rights.values()),
        dangers=list(dangers.values()),
        benefits=list(benefits.values()),
        recommended_actions=list(recommended_actions.values()),
        privacy_signals=accumulated_signals,
        retention_policy=list(retention_policy.values()),
        security_measures=list(security_measures.values()),
        advertising_practices=list(advertising_practices.values()),
        profiling_ai=list(profiling_ai.values()),
        contract_clauses=list(contract_clauses.values()),
    )
    logger.debug(
        f"Extraction complete for document {document.id} "
        f"(data_collected={len(extraction.data_collected)}, "
        f"data_purposes={len(extraction.data_purposes)}, "
        f"rights={len(extraction.your_rights)}, dangers={len(extraction.dangers)}, "
        f"benefits={len(extraction.benefits)}, actions={len(extraction.recommended_actions)}, "
        f"third_parties={len(extraction.third_party_details)}, "
        f"contract_clauses={len(extraction.contract_clauses)})"
    )

    document.extraction = extraction
    # Also store extraction metadata for debugging / cache busting
    document.metadata["extraction_version"] = extraction.version
    document.metadata["extraction_generated_at"] = extraction.generated_at.isoformat()
    document.metadata["extraction_source_hash"] = content_hash
    logger.debug(
        f"Stored extraction metadata for document {document.id} "
        f"(version={extraction.version}, source_hash={content_hash})"
    )

    return extraction
