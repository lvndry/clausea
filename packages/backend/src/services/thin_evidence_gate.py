"""Thin-evidence gate: blocks overview generation when evidence is insufficient."""

from __future__ import annotations

from src.prompts.analysis_prompts import OVERVIEW_CORE_DOC_TYPES

MIN_DISTINCT_CORE_TYPES = 2
MIN_TOTAL_CORE_DOCS = 3


def check_thin_evidence(analyzed_core_docs: list[str]) -> tuple[bool, str | None]:
    """Returns (is_thin, reason). Thin when <2 core doc types or <3 analyzed core docs total."""

    core_doc_types = [
        doc_type for doc_type in analyzed_core_docs if doc_type in OVERVIEW_CORE_DOC_TYPES
    ]
    distinct_type_count = len(set(core_doc_types))
    total_core_count = len(core_doc_types)

    if distinct_type_count < MIN_DISTINCT_CORE_TYPES or total_core_count < MIN_TOTAL_CORE_DOCS:
        if total_core_count == 0:
            return True, "No core policy documents have been analyzed yet."
        return True, (
            f"Only {distinct_type_count} distinct core document type(s) "
            f"across {total_core_count} document(s) analyzed — at least "
            f"{MIN_DISTINCT_CORE_TYPES} distinct types and {MIN_TOTAL_CORE_DOCS} "
            f"documents are required for a reliable overview."
        )

    return False, None
