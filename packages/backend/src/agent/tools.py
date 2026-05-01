from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from src.core.logging import get_logger
from src.llm import acompletion_with_fallback, get_embeddings
from src.pinecone_client import INDEX_NAME, pc
from src.prompts.policy_understanding_prompts import (
    POLICY_USER_ANALYSIS_JSON_SCHEMA,
    POLICY_USER_ANALYSIS_PROMPT,
    USER_POLICY_RETRIEVAL_QUERIES,
)

logger = get_logger(__name__)


def _truncate(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "\n\n[... truncated ...]"


def format_matches_for_context(matches: list[dict[str, Any]], *, max_chars: int) -> str:
    """Format Pinecone matches into a compact, citation-friendly context block.

    Each source is labeled SOURCE[N] with url, document type, and char offsets
    so the model can produce traceable citations in its answer.
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
    ns = namespace or product_slug

    # Pinecone client is synchronous; run in a worker thread to avoid blocking the event loop.
    def _query() -> dict[str, Any]:
        index = pc.Index(INDEX_NAME)
        return index.query(  # type: ignore[no-any-return]
            namespace=ns,
            top_k=top_k,
            vector=query_vector,
            include_metadata=True,
            include_values=False,
        )

    search_results = await asyncio.to_thread(_query)

    return search_results  # type: ignore


async def analyze_policy_documents(
    product_slug: str,
    *,
    focus: str | None = None,
    regulation_context: str | None = None,
) -> str:
    """
    Chat-only: run many embedding searches (see `policy_understanding_prompts`) and
    synthesize a fresh pass for the agent.

    The product page overview is **not** produced here — it comes from the post-crawl
    pipeline (`generate_product_overview` + cached `MetaSummary`).
    """
    queries = list(USER_POLICY_RETRIEVAL_QUERIES)
    if focus and focus.strip():
        queries.append(focus.strip())
    if regulation_context and regulation_context.strip():
        rc = regulation_context.strip()
        queries.append(
            f"{rc} privacy notice transparency data subject rights disclosure expectations"
        )

    search_tasks = [search_query(q, product_slug, top_k=3) for q in queries]
    results = await asyncio.gather(*search_tasks, return_exceptions=True)

    best_by_key: dict[tuple[str, int, int], dict[str, Any]] = {}
    for res in results:
        if isinstance(res, BaseException):
            logger.warning(f"Policy analysis search failed: {res}")
            continue
        res_dict = cast(dict[str, Any], res)
        for match in res_dict.get("matches", []) or []:
            md = match.get("metadata", {}) or {}
            url = str(md.get("url", ""))
            start = int(md.get("chunk_start") or 0)
            end = int(md.get("chunk_end") or 0)
            key = (url, start, end)
            existing_score = (
                float(best_by_key[key].get("score", 0.0)) if key in best_by_key else -1.0
            )
            if float(match.get("score", 0.0)) > existing_score:
                best_by_key[key] = match

    if not best_by_key:
        return "I couldn't find enough policy text in the index to summarize. Try crawling or indexing first."

    top_matches = sorted(
        best_by_key.values(), key=lambda m: float(m.get("score", 0.0)), reverse=True
    )
    context = format_matches_for_context(top_matches, max_chars=1500)

    focus_block = focus.strip() if focus and focus.strip() else "(None — give a balanced overview.)"
    reg_block = (
        regulation_context.strip()
        if regulation_context and regulation_context.strip()
        else "(None — set regulation_plain_language_note to null in JSON.)"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You explain policy documents (privacy, terms, cookies, community rules, safety, etc.) "
                "to thoughtful everyday readers. You are not conducting a regulatory compliance audit "
                "and you do not give legal advice."
            ),
        },
        {
            "role": "user",
            "content": POLICY_USER_ANALYSIS_PROMPT.format(
                context=context,
                focus=focus_block,
                regulation_context=reg_block,
                schema=POLICY_USER_ANALYSIS_JSON_SCHEMA,
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

        parts: list[str] = []
        parts.append(
            "**What this means for you** (from the organization's published documents — not legal advice)\n"
        )
        hs = parsed.get("headline_summary")
        if hs:
            parts.append(f"{hs}\n")

        agree = parsed.get("what_you_agree_to") or []
        if agree:
            parts.append("**What you may be agreeing to**")
            parts.extend([f"- {x}" for x in agree[:12]])

        risks = parsed.get("risks_and_watchouts") or []
        if risks:
            parts.append("\n**Risks and watch-outs**")
            for r in risks[:10]:
                if isinstance(r, dict):
                    sev = r.get("severity", "")
                    title = r.get("title", "")
                    detail = r.get("detail", "")
                    parts.append(f"- **{title}** ({sev}): {detail}")
                else:
                    parts.append(f"- {r}")

        unusual = parsed.get("unusual_or_notable_clauses") or []
        if unusual:
            parts.append("\n**Unusual or worth reading closely**")
            parts.extend([f"- {x}" for x in unusual[:8]])

        rights = parsed.get("your_rights_and_choices") or []
        if rights:
            parts.append("\n**What the documents say you can do**")
            parts.extend([f"- {x}" for x in rights[:10]])

        unclear = parsed.get("whats_unclear_or_missing") or []
        if unclear:
            parts.append("\n**Unclear or not covered in what we retrieved**")
            parts.extend([f"- {x}" for x in unclear[:8]])

        reg_note = parsed.get("regulation_plain_language_note")
        if reg_note:
            rc = (regulation_context or "").strip()
            heading = (
                f"**How this compares to common {rc} notice expectations** (educational only)"
                if rc
                else "**Regulatory framing** (educational only)"
            )
            parts.append(f"\n{heading}\n{reg_note}")

        lim = parsed.get("limitations")
        if lim:
            parts.append(f"\n**Limits of this summary**\n{lim}")

        parts.append("\n**Sources used:**")
        for i, m in enumerate(top_matches, start=1):
            md = m.get("metadata", {}) or {}
            parts.append(
                f"- SOURCE[{i}] {md.get('document_type', 'Unknown')} {md.get('url', 'Unknown')} "
                f"(chars {md.get('chunk_start', '')}-{md.get('chunk_end', '')})"
            )
        return "\n".join(parts)
    except Exception as e:
        logger.error(f"Error in analyze_policy_documents: {e}")
        return f"Error analyzing policy documents: {e}"
