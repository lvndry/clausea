"""Utilities that support the chunked extraction pipeline: validation, chunking, evidence.

**What it does**
- ``_extraction_validator(result)``: validates the shape of an LLM extraction response
  (must be a dict with ``privacy_signals``, ``data_items``, etc.), returning the
  parsed ``ExtractionResult`` or raising a clear error.
- ``_chunk_text(text, max_chunk_size, overlap)``: splits a long document into
  overlapping chunks that fit within the LLM context window, preserving sentence
  boundaries where possible.
- ``resolve_quote_offsets(document_text, quotes)``: maps extracted quote strings
  back to byte/character offsets in the original document for evidence rendering.

**What it contains**
- ``_extraction_validator`` function.
- ``_chunk_text`` function.
- ``_add_evidence`` helper that records which quote contributed to each merged
  signal (called from ``merging.py``).
- Imports from ``src.utils.quotes`` for offset resolution.

**What it allows/prevents**
Allows the extraction service to handle documents of arbitrary length by splitting
into model-sized chunks.  Prevents malformed LLM output from propagating silently
into the merge stage.
"""

import hashlib
import json
import re

from src.core.logging import get_logger
from src.models.document import Document, EvidenceSpan
from src.utils.quotes import resolve_quote_offsets

logger = get_logger(__name__)

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


def _extraction_validator(cluster_name: str):
    """A cluster response is valid when it is well-formed, even if empty.

    A chunk often has no content for a given cluster (e.g. a cookie page has nothing for
    legal_scope), and the model correctly returns empty lists. That is NOT a failure, so
    it must not escalate through the whole model cascade — only malformed/unparseable
    output, a non-dict, or output with no list-shaped expected key escalates.
    """
    required = _CLUSTER_REQUIRED_KEYS.get(cluster_name, [])

    def validate(content: str) -> bool:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        expected_keys = required or list(data.keys())
        return any(isinstance(data.get(key), list) for key in expected_keys)

    return validate


def _compute_content_hash(document: Document) -> str:
    content = f"{document.markdown}{document.doc_type}"
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


def _make_evidence(document: Document, content_hash: str, quote: str) -> EvidenceSpan:
    start_char, end_char, verified = resolve_quote_offsets(document.markdown, quote)
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


__all__ = [
    "_chunk_text",
    "_compute_content_hash",
    "_extraction_validator",
    "_make_evidence",
    "_split_on_sentence_boundary",
]
