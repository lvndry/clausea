"""Semantic consolidation of cross-document rollup findings.

Exact-key aggregation collapses findings whose normalized text is identical, but
the same clause extracted from different documents produces paraphrases that never
match — "User grants Bumble a licence…", "Users grant Bumble a license…", and
"Uploading Pitch Content grants Bumble a license…" are three phrasings of one
clause. String and structured-attribute keys cannot separate these from genuinely
distinct findings: a clause that adds "AI training" can be more string-similar to
its sibling than two true paraphrases are to each other. The merge boundary is
semantic, so an LLM judge decides it.

This stage runs once at rollup-build time and persists merged ``RollupItem``s, so
read-time hydration and topic reports inherit the result with no per-read cost.

Approach
--------
Cheap exact-key aggregation runs first and collapses byte-identical findings for
free. Only the survivors, grouped per category, reach this stage — and only for
free-text narrative categories where paraphrase duplication actually happens
(``CONSOLIDATION_CATEGORIES``); structured categories (data types, named
recipients, enumerated rights) are distinct by construction and skipped. The
merge decision itself is delegated to an LLM judge because it is semantic, not
lexical: the judge partitions a category's findings into clusters that each
restate one underlying clause, and is instructed to keep any materially distinct
right/permission/scope/purpose (AI training, sale, sublicensing, perpetuity) in
its own cluster.

Steps
-----
1. Group the aggregated findings by category; skip any category with fewer than
   two findings or outside ``CONSOLIDATION_CATEGORIES``.
2. Ask the LLM judge to partition the category's finding values into same-clause
   clusters (``_llm_cluster`` → ``_parse_clusters``).
3. Merge each cluster into one ``RollupItem`` (``merge_clusters``): pick the most
   complete member as the canonical value, union document ids and attributes, and
   record every member's normalised value in ``member_values``.
4. ``member_values`` lets read-time hydration re-attach evidence from *all* source
   documents, not just the canonical member — so a "stated in N documents" finding
   keeps all N quotes.

Any judge failure degrades to the original, unmerged findings: consolidation never
drops a finding on error.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Awaitable, Callable

from src.core.logging import get_logger
from src.llm import acompletion_with_fallback
from src.models.document import InsightCategory
from src.models.product_intelligence import RollupItem
from src.services.product_rollup_service import ProductRollupService

logger = get_logger(__name__)

ClusterJudge = Callable[[InsightCategory, list[str]], Awaitable[list[list[int]]]]

# Deadline for one judge call so a hung model can't stall the whole rollup build.
_JUDGE_TIMEOUT_SECONDS = 30

# Cap on merged attributes; must not exceed RollupItem.attributes max_length (50).
_MAX_MERGED_ATTRIBUTES = 50

# Higher rank wins when materiality attributes are ordered before capping.
_MATERIALITY_RANK: dict[str, int] = {
    "material_risk": 3,
    "notable": 2,
    "standard_industry": 1,
}

# Free-text narrative categories where the same clause recurs across documents as
# paraphrases. Structured categories (data_collection types, named recipients,
# enumerated rights) are excluded — their findings are distinct by construction.
CONSOLIDATION_CATEGORIES: frozenset[str] = frozenset(
    {
        "content_ownership",
        "dangers",
        "scope_expansion",
        "liability",
        "termination_consequences",
        "indemnification",
        "dispute_resolution",
        "benefits",
        "recommended_actions",
        "data_purposes",
    }
)

_JUDGE_SYSTEM_PROMPT = """You group policy findings that state the SAME underlying clause.

You receive a numbered list of findings for one topic. Partition them into groups where each group restates ONE underlying clause, obligation, or permission.

Two findings belong in the same group ONLY when they describe the same right, permission, scope, and purpose — differing only in wording, document of origin, or singular/plural phrasing.

If a finding asserts a materially distinct right, permission, scope, or purpose that another does not — for example AI training, data sale, sublicensing, a perpetual term, a different feature, or a different data type — it MUST be in its own group, even when the wording is very similar. When in doubt, keep findings separate; never merge away a distinction a careful reader would want.

Return JSON only, covering every index exactly once, no index repeated:
{"clusters": [[0], [1, 2, 4], [3]]}"""


async def _llm_cluster(
    category: InsightCategory,
    values: list[str],
    *,
    circuit_key: str | None = None,
) -> list[list[int]]:
    numbered = "\n".join(f"{index}. {value}" for index, value in enumerate(values))
    user_payload = f'Topic: "{category}"\n\nFindings:\n{numbered}'
    response = await acompletion_with_fallback(
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_payload},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        timeout=_JUDGE_TIMEOUT_SECONDS,
        circuit_key=circuit_key,
    )
    choice = response.choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None) if message else None
    if not content:
        raise ValueError("Empty consolidation response")
    return _parse_clusters(json.loads(content), expected_count=len(values))


def _parse_clusters(parsed: object, *, expected_count: int) -> list[list[int]]:
    clusters_raw = parsed.get("clusters") if isinstance(parsed, dict) else None
    if not isinstance(clusters_raw, list):
        raise ValueError("Consolidation response missing 'clusters' list")

    clusters: list[list[int]] = []
    seen: set[int] = set()
    for group in clusters_raw:
        if not isinstance(group, list):
            continue
        indices = []
        for raw_index in group:
            if not isinstance(raw_index, int) or not (0 <= raw_index < expected_count):
                continue
            if raw_index in seen:
                logger.warning("Consolidation judge returned a duplicate index", index=raw_index)
                continue
            seen.add(raw_index)
            indices.append(raw_index)
        if indices:
            clusters.append(indices)

    for index in range(expected_count):
        if index not in seen:
            clusters.append([index])
    return clusters


def _merge_attributes(members: list[RollupItem]) -> list[dict]:
    """Combine members' attributes, deduplicated and ordered so capping never drops
    the strongest materiality signal that downstream danger-filtering reads."""
    seen: set[str] = set()
    deduped: list[dict] = []
    for member in members:
        for attribute in member.attributes:
            key = json.dumps(attribute, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(attribute)
    deduped.sort(
        key=lambda attribute: _MATERIALITY_RANK.get(str(attribute.get("materiality")), 0),
        reverse=True,
    )
    return deduped[:_MAX_MERGED_ATTRIBUTES]


def _merge_cluster(members: list[RollupItem]) -> RollupItem:
    pivot = max(members, key=lambda item: len(item.value))
    document_ids = list(
        dict.fromkeys(doc_id for member in members for doc_id in member.document_ids)
    )
    member_values = list(
        dict.fromkeys(ProductRollupService._normalize_value(member.value) for member in members)
    )
    return RollupItem(
        category=pivot.category,
        value=pivot.value,
        document_ids=document_ids,
        attributes=_merge_attributes(members),
        confidence=pivot.confidence,
        member_values=member_values,
    )


def merge_clusters(items: list[RollupItem], clusters: list[list[int]]) -> list[RollupItem]:
    """Merge each cluster of indices into one RollupItem; single-item clusters pass through."""
    merged: list[RollupItem] = []
    for cluster in clusters:
        members = [items[index] for index in cluster if 0 <= index < len(items)]
        if not members:
            continue
        if len(members) == 1:
            merged.append(members[0])
        else:
            merged.append(_merge_cluster(members))
    return merged


async def consolidate_rollup_items(
    items: list[RollupItem],
    *,
    judge: ClusterJudge | None = None,
    circuit_key: str | None = None,
) -> list[RollupItem]:
    """Merge paraphrase-duplicate findings per category using an LLM judge.

    Categories outside :data:`CONSOLIDATION_CATEGORIES` and categories with fewer
    than two findings pass through untouched. Any judge failure degrades to the
    original items — consolidation never drops findings on error.
    """
    if judge is None:
        key = circuit_key

        async def _default_judge(category: InsightCategory, values: list[str]) -> list[list[int]]:
            return await _llm_cluster(category, values, circuit_key=key)

        chosen_judge = _default_judge
    else:
        chosen_judge = judge

    by_category: defaultdict[InsightCategory, list[RollupItem]] = defaultdict(list)
    order: list[InsightCategory] = []
    for item in items:
        if item.category not in by_category:
            order.append(item.category)
        by_category[item.category].append(item)

    result: list[RollupItem] = []
    for category in order:
        group = by_category[category]
        if len(group) < 2 or category not in CONSOLIDATION_CATEGORIES:
            result.extend(group)
            continue
        try:
            clusters = await chosen_judge(category, [item.value for item in group])
            merged = merge_clusters(group, clusters)
        except Exception as exc:
            logger.warning(
                "Finding consolidation failed; keeping unmerged",
                category=category,
                error=str(exc),
            )
            result.extend(group)
            continue
        if len(merged) < len(group):
            logger.info(
                "Consolidated findings",
                category=category,
                before=len(group),
                after=len(merged),
            )
        result.extend(merged)
    return result


__all__ = [
    "CONSOLIDATION_CATEGORIES",
    "consolidate_rollup_items",
    "merge_clusters",
]
