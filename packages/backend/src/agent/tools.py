from __future__ import annotations

import json
from typing import Any

from src.core.logging import get_logger
from src.llm import acompletion_with_fallback, get_embeddings
from src.pinecone_client import INDEX_NAME, pc
from src.prompts.compliance_prompts import COMPLIANCE_CHECK_JSON_SCHEMA, COMPLIANCE_CHECK_PROMPT

logger = get_logger(__name__)


def _truncate(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "\n\n[... truncated ...]"


def _format_matches_for_context(matches: list[dict[str, Any]], *, max_chars: int) -> str:
    """
    Format Pinecone matches into a compact, citation-friendly context format:
    SOURCE[1] url=... type=... chars=start-end
    excerpt: ...
    """
    chunks: list[str] = []
    for i, match in enumerate(matches, start=1):
        md = match.get("metadata", {}) or {}
        url = md.get("url", "Unknown")
        doc_type = md.get("document_type", "Unknown")
        start = md.get("chunk_start", "")
        end = md.get("chunk_end", "")
        excerpt = _truncate(str(md.get("chunk_text", "") or ""), max_chars=max_chars)
        chunks.append(
            f"SOURCE[{i}] url={url} type={doc_type} chars={start}-{end}\nexcerpt:\n{excerpt}"
        )
    return "\n\n---\n\n".join(chunks)


REGULATION_QUERIES: dict[str, list[str]] = {
    "GDPR": [
        "GDPR lawful basis consent contract legal obligation legitimate interests",
        "GDPR data subject rights access rectification erasure portability objection",
        "international transfers SCC adequacy data transfer outside EEA",
        "DPO data protection officer representative EU",
        "data breach notification 72 hours",
    ],
    "CCPA": [
        "CCPA sale sell share opt out Do Not Sell My Personal Information",
        "CCPA categories of personal information collected disclosed",
        "right to know request disclosure delete",
        "non-discrimination for exercising rights",
    ],
    "PIPEDA": [
        "PIPEDA consent purposes collection use disclosure",
        "PIPEDA safeguards security measures protect personal information",
        "PIPEDA access request correction individual access",
        "accountability privacy officer",
    ],
    "LGPD": [
        "LGPD legal basis consent legitimate interest",
        "LGPD data subject rights access correction deletion portability",
        "DPO encarregado",
        "international transfer",
        "security measures incident notification",
    ],
}


async def embed_query(query: str) -> list[float]:
    """
    Convert a text query into vector embeddings.

    Args:
        query: The text query to embed

    Returns:
        list[float]: The vector embedding of the query
    """
    try:
        response = await get_embeddings(
            input=query,
            input_type="query",
        )

        return response.data[0]["embedding"]  # type: ignore
    except Exception as e:
        logger.error(f"Error getting embeddings: {str(e)}")
        raise


async def search_query(
    query: str, product_slug: str, top_k: int = 8, *, namespace: str | None = None
) -> dict[str, Any]:
    """
    Search for relevant documents in Pinecone.

    Args:
        query: The search query
        product_slug: The product slug (used as namespace if namespace not provided)
        top_k: Number of results to return
        namespace: Optional specific namespace

    Returns:
        dict: Pinecone search results
    """
    # Convert text query to vector embedding
    query_vector = await embed_query(query)
    index = pc.Index(INDEX_NAME)
    ns = namespace or product_slug
    search_results = index.query(
        namespace=ns,
        top_k=top_k,
        vector=query_vector,
        include_metadata=True,
        include_values=False,
    )

    return search_results  # type: ignore


async def check_compliance(regulation: str, product_slug: str) -> str:
    """
    Check if the product's documents comply with a specific regulation.

    Args:
        regulation: The regulation to check (e.g., "GDPR", "CCPA")
        product_slug: The product slug to search within

    Returns:
        str: Assessment of compliance
    """
    # 1) Targeted retrieval: run several focused queries and merge results.
    reg = regulation.strip().upper()
    queries = REGULATION_QUERIES.get(reg, [f"{regulation} privacy compliance data rights"])
    merged: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int, int]] = set()

    for q in queries:
        res = await search_query(q, product_slug, top_k=5)
        for match in res.get("matches", []) or []:
            md = match.get("metadata", {}) or {}
            url = str(md.get("url", ""))
            start = int(md.get("chunk_start") or 0)
            end = int(md.get("chunk_end") or 0)
            key = (url, start, end)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(match)

    if not merged:
        return f"I couldn't find enough information to assess {regulation} compliance."

    # Keep the most relevant chunks; also hard-cap per excerpt to control token usage.
    merged.sort(key=lambda m: float(m.get("score", 0.0)), reverse=True)
    top_matches = merged[:12]
    context = _format_matches_for_context(top_matches, max_chars=1100)

    # 2) Ask LLM to assess (structured JSON output).
    messages = [
        {"role": "system", "content": "You are a legal compliance expert."},
        {
            "role": "user",
            "content": COMPLIANCE_CHECK_PROMPT.format(
                regulation=regulation,
                context=context,
                schema=COMPLIANCE_CHECK_JSON_SCHEMA,
            ),
        },
    ]

    try:
        response = await acompletion_with_fallback(
            messages=messages,
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
        parsed = json.loads(str(content))
        status = parsed.get("status", "Unknown")
        score = parsed.get("score", "unknown")
        strengths = parsed.get("strengths") or []
        gaps = parsed.get("gaps") or []
        limitations = parsed.get("limitations") or []

        # Return a compact, user-facing summary. (The Agent can rephrase further.)
        parts: list[str] = []
        parts.append(f"{regulation} compliance: {status} (score {score}/10)")
        if strengths:
            parts.append("\nStrengths:")
            parts.extend([f"- {s}" for s in strengths[:6]])
        if gaps:
            parts.append("\nGaps / concerns:")
            parts.extend([f"- {g}" for g in gaps[:6]])
        if limitations:
            parts.append("\nLimitations (missing evidence in retrieved excerpts):")
            parts.extend([f"- {limitation}" for limitation in limitations[:6]])
        parts.append("\nSources used:")
        for i, m in enumerate(top_matches, start=1):
            md = m.get("metadata", {}) or {}
            parts.append(
                f"- SOURCE[{i}] {md.get('document_type', 'Unknown')} {md.get('url', 'Unknown')} "
                f"(chars {md.get('chunk_start', '')}-{md.get('chunk_end', '')})"
            )
        return "\n".join(parts)
    except Exception as e:
        logger.error(f"Error checking compliance: {e}")
        return f"Error checking compliance: {str(e)}"
