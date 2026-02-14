"""Evidence-first extraction for legal documents.

This service extracts structured facts from a document WITH evidence (exact quotes),
so downstream summaries can be generated from extracted facts only.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.core.logging import get_logger
from src.llm import SupportedModel, acompletion_with_fallback
from src.models.document import (
    Document,
    DocumentExtraction,
    EvidenceSpan,
    ExtractedDataPurposeLink,
    ExtractedTextItem,
    ExtractedThirdPartyRecipient,
)
from src.utils.cancellation import CancellationToken

logger = get_logger(__name__)


def _compute_content_hash(document: Document) -> str:
    """Keep hashing consistent with summarizer caching (text + doc_type)."""
    content = f"{document.text}{document.doc_type}"
    return hashlib.sha256(content.encode()).hexdigest()


def _chunk_text(text: str, *, chunk_size: int = 8000, overlap: int = 800) -> list[str]:
    if not text:
        return []
    if chunk_size <= 0:
        return [text]
    overlap = max(0, min(overlap, chunk_size - 1))

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


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


class _ExtractionChunkResult(BaseModel):
    data_collected: list[_ExtractionItem] = Field(default_factory=list)
    data_purposes: list[_ExtractionItem] = Field(default_factory=list)
    data_collection_details: list[_ExtractionDataPurposeLink] = Field(default_factory=list)
    third_party_details: list[_ExtractionThirdParty] = Field(default_factory=list)
    your_rights: list[_ExtractionItem] = Field(default_factory=list)
    dangers: list[_ExtractionItem] = Field(default_factory=list)
    benefits: list[_ExtractionItem] = Field(default_factory=list)
    recommended_actions: list[_ExtractionItem] = Field(default_factory=list)


EXTRACTION_SYSTEM_PROMPT = """You are an expert legal-document information extractor.

Your job is to extract structured facts ONLY from the provided text chunk.

Critical rules:
- Only extract items explicitly present in the text chunk.
- For every extracted item, provide an evidence quote that is an EXACT substring of the provided chunk.
- If a field is not present, return an empty list for that field.
- Do not paraphrase evidence quotes; copy exact text.
"""


def _extraction_user_prompt(document: Document, chunk: str) -> str:
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
        "third_party_details": [
            {
                "recipient": "Advertisers",
                "data_shared": ["email", "location data"],
                "purpose": "Targeted advertising",
                "risk_level": "high",
                "quote": "exact quote",
            }
        ],
        "your_rights": [{"value": "Delete your account via ...", "quote": "exact quote"}],
        "dangers": [{"value": "No retention period specified", "quote": "exact quote"}],
        "benefits": [{"value": "Encryption in transit", "quote": "exact quote"}],
        "recommended_actions": [{"value": "Opt out of ads via ...", "quote": "exact quote"}],
    }

    return f"""
Extract evidence-backed facts from this legal document chunk.

Document URL: {document.url}
Document Type: {document.doc_type}

Text chunk:
{chunk}

Return a JSON object with these keys (all keys required):
{json.dumps(schema_hint, indent=2)}

Notes:
- `risk_level` must be one of: low, medium, high (optional if unclear).
- Keep `value` short and normalized (deduplicate variants like "e-mail" vs "email").
- Evidence quotes must be EXACT substrings of the chunk.
""".strip()


def _dedupe_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


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


async def extract_document_facts(
    document: Document,
    *,
    use_cache: bool = True,
    model_priority: list[SupportedModel] | None = None,
    cancellation_token: CancellationToken | None = None,
) -> DocumentExtraction:
    """Extract evidence-backed facts from a document.

    This is safe to call inside request handlers (supports cancellation), but may be slow
    depending on document length.
    """
    token = cancellation_token or CancellationToken()

    content_hash = (
        document.metadata.get("content_hash") if document.metadata else None
    ) or _compute_content_hash(document)

    if (
        use_cache
        and document.extraction
        and document.extraction.source_content_hash == content_hash
    ):
        return document.extraction

    text = document.text or ""
    chunks = _chunk_text(text, chunk_size=8000, overlap=800)
    if not chunks:
        extraction = DocumentExtraction(
            version="v1",
            generated_at=datetime.now(),
            source_content_hash=content_hash,
        )
        document.extraction = extraction
        return extraction

    # Merge maps
    data_collected: dict[str, ExtractedTextItem] = {}
    data_purposes: dict[str, ExtractedTextItem] = {}
    your_rights: dict[str, ExtractedTextItem] = {}
    dangers: dict[str, ExtractedTextItem] = {}
    benefits: dict[str, ExtractedTextItem] = {}
    recommended_actions: dict[str, ExtractedTextItem] = {}
    data_collection_details: dict[str, ExtractedDataPurposeLink] = {}
    third_party_details: dict[str, ExtractedThirdPartyRecipient] = {}

    for idx, chunk in enumerate(chunks, 1):
        await token.check_cancellation()
        logger.debug(f"Extracting facts for {document.id}: chunk {idx}/{len(chunks)}")

        response = await acompletion_with_fallback(
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": _extraction_user_prompt(document, chunk)},
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

        parsed: dict[str, Any] = json.loads(content)
        chunk_result = _ExtractionChunkResult.model_validate(parsed, strict=False)

        _merge_text_items(
            data_collected,
            chunk_result.data_collected,
            document=document,
            content_hash=content_hash,
        )
        _merge_text_items(
            data_purposes, chunk_result.data_purposes, document=document, content_hash=content_hash
        )
        _merge_text_items(
            your_rights, chunk_result.your_rights, document=document, content_hash=content_hash
        )
        _merge_text_items(
            dangers, chunk_result.dangers, document=document, content_hash=content_hash
        )
        _merge_text_items(
            benefits, chunk_result.benefits, document=document, content_hash=content_hash
        )
        _merge_text_items(
            recommended_actions,
            chunk_result.recommended_actions,
            document=document,
            content_hash=content_hash,
        )
        _merge_data_purpose_links(
            data_collection_details,
            chunk_result.data_collection_details,
            document=document,
            content_hash=content_hash,
        )
        _merge_third_parties(
            third_party_details,
            chunk_result.third_party_details,
            document=document,
            content_hash=content_hash,
        )

    extraction = DocumentExtraction(
        version="v1",
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
    )

    document.extraction = extraction
    # Also store extraction metadata for debugging / cache busting
    document.metadata["extraction_version"] = extraction.version
    document.metadata["extraction_generated_at"] = extraction.generated_at.isoformat()
    document.metadata["extraction_source_hash"] = content_hash

    return extraction
