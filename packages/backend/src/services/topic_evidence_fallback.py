"""Recover supporting citations for topic stances from document extractions.

Some topic stances are marked ``found`` but end up with zero supporting
citations because the analyser's finding→citation linkage misses certain
``InsightCategory`` values. Rather than leave those overview cards without a
source, this module reads evidence spans directly from each document's
``DocumentExtraction`` fields and attaches up to three citations per stance.

Accepts ``TopicStanceBreakdown`` models or plain dicts, and ``Document`` models
or plain dicts, so it can run against freshly built overviews and persisted
dicts loaded from storage.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from src.models.document import Document, TopicStanceBreakdown, TopicSupportCitation

FALLBACK_CITATION_LIMIT = 3


class _ExtractionField(NamedTuple):
    field: str
    single: bool = False
    purpose_keyword: str | None = None


_TOPIC_EXTRACTION_FIELDS: dict[str, list[_ExtractionField]] = {
    "data_collection": [_ExtractionField(field="data_collected")],
    "data_sharing": [_ExtractionField(field="third_party_details")],
    "ai_training": [_ExtractionField(field="ai_usage")],
    "retention": [_ExtractionField(field="retention_policies")],
    "security": [_ExtractionField(field="security_measures")],
    "children": [_ExtractionField(field="children_policy", single=True)],
    "government_access": [_ExtractionField(field="government_access")],
    "international_transfers": [_ExtractionField(field="international_transfers")],
    "content_ownership": [_ExtractionField(field="content_ownership")],
    "liability": [_ExtractionField(field="liability")],
    "dispute_resolution": [_ExtractionField(field="dispute_resolution")],
    "consent_mechanisms": [_ExtractionField(field="consent_mechanisms")],
    "user_rights": [_ExtractionField(field="user_rights")],
    "cookies_tracking": [_ExtractionField(field="cookies_and_trackers")],
    "advertising": [_ExtractionField(field="data_purposes", purpose_keyword="advertising")],
    "data_sale": [
        _ExtractionField(field="data_purposes", purpose_keyword="sale"),
        _ExtractionField(field="third_party_details"),
    ],
}


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _item_evidence(item: Any) -> list[Any]:
    return list(_get_attr(item, "evidence", None) or [])


def _field_items(extraction: Any, spec: _ExtractionField) -> list[Any]:
    raw = _get_attr(extraction, spec.field, None)
    if spec.single:
        return [raw] if raw is not None else []
    items = list(raw or [])
    if spec.purpose_keyword is None:
        return items
    keyword = spec.purpose_keyword
    matched: list[Any] = []
    for item in items:
        purposes = _get_attr(item, "purposes", None) or []
        purposes_lower = [str(purpose).lower() for purpose in purposes]
        if keyword in purposes_lower:
            matched.append(item)
    return matched


def _build_citation(document: Any, span: Any) -> TopicSupportCitation:
    return TopicSupportCitation(
        document_id=str(_get_attr(document, "id", "") or ""),
        document_title=_get_attr(document, "title", None),
        document_url=_get_attr(document, "url", None),
        quote=str(_get_attr(span, "quote", "") or ""),
        section_title=_get_attr(span, "section_title", None),
        verified=True,
    )


def _collect_citations(topic: str, documents: list[Any]) -> list[TopicSupportCitation]:
    specs = _TOPIC_EXTRACTION_FIELDS.get(topic)
    if not specs:
        return []
    citations: list[TopicSupportCitation] = []
    seen: set[tuple[str, str]] = set()
    for document in documents:
        extraction = _get_attr(document, "extraction", None)
        if extraction is None:
            continue
        for spec in specs:
            for item in _field_items(extraction, spec):
                for span in _item_evidence(item):
                    quote = str(_get_attr(span, "quote", "") or "").strip()
                    if not quote:
                        continue
                    document_id = str(_get_attr(document, "id", "") or "")
                    key = (document_id, quote)
                    if key in seen:
                        continue
                    seen.add(key)
                    citations.append(_build_citation(document, span))
                    if len(citations) >= FALLBACK_CITATION_LIMIT:
                        return citations
    return citations


def _set_citations(stance: Any, citations: list[TopicSupportCitation]) -> None:
    if isinstance(stance, dict):
        stance["supporting_citations"] = citations
    else:
        stance.supporting_citations = citations


async def attach_fallback_evidence(
    topic_stances: list[TopicStanceBreakdown],
    documents: list[Document],
) -> int:
    """For topic_stances with status='found' but 0 supporting_citations,
    search the documents' extractions for evidence matching the topic category
    and attach citations.

    Returns the number of citations attached.
    """
    attached_total = 0
    for stance in topic_stances:
        status = _get_attr(stance, "status", None)
        if status != "found":
            continue
        existing = _get_attr(stance, "supporting_citations", None) or []
        if len(existing) > 0:
            continue
        topic = _get_attr(stance, "topic", None)
        if topic is None:
            continue
        citations = _collect_citations(str(topic), documents)
        if not citations:
            continue
        _set_citations(stance, citations)
        attached_total += len(citations)
    return attached_total
