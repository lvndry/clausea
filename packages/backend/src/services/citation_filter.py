"""Filter product overview topic stances down to displayable citations.

Hides citations that are no longer trustworthy so the product overview UI never
surfaces a source the user cannot rely on:

* ``verified=False`` — the quote string does not match the stored extraction, so
  the citation cannot be confirmed against the source text.
* ``stale=True``      — the source document was deleted or superseded on re-crawl,
  so the ``document_id`` no longer resolves to a real document.

Topic stances are always retained: when every citation is filtered out the
stance is kept with an empty ``supporting_citations`` list so the topic card
still renders, just without a source link. Accepts ``TopicStanceBreakdown``
models or plain dicts.
"""

from __future__ import annotations

from typing import Any


def _is_displayable(citation: Any) -> bool:
    if isinstance(citation, dict):
        verified = citation.get("verified", True)
        stale = citation.get("stale", False)
    else:
        verified = getattr(citation, "verified", True)
        stale = getattr(citation, "stale", False)
    return bool(verified) and not bool(stale)


def _get_citations(stance: Any) -> list[Any]:
    if isinstance(stance, dict):
        return list(stance.get("supporting_citations") or [])
    return list(getattr(stance, "supporting_citations", None) or [])


def _with_citations(stance: Any, citations: list[Any]) -> Any:
    if isinstance(stance, dict):
        copy = dict(stance)
        copy["supporting_citations"] = citations
        return copy
    return stance.model_copy(update={"supporting_citations": citations})


def filter_topic_stance_citations(topic_stances: list[Any]) -> list[Any]:
    """Return topic stances with only verified, non-stale supporting citations.

    For each topic stance, ``supporting_citations`` is reduced to entries where
    ``verified`` is True and ``stale`` is not True. Topic stances with no
    surviving citations are kept with an empty ``supporting_citations`` list so
    the card still renders without a source link. The input list is not mutated.
    """
    filtered: list[Any] = []
    for stance in topic_stances:
        kept = [cite for cite in _get_citations(stance) if _is_displayable(cite)]
        filtered.append(_with_citations(stance, kept))
    return filtered
