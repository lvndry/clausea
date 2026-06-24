"""HTML main-content extraction via trafilatura."""

from __future__ import annotations

from trafilatura.core import bare_extraction, determine_returnstring
from trafilatura.metadata import Document
from trafilatura.settings import Extractor, use_config

MIN_TRAFILATURA_CHARS = 200


def extract_with_trafilatura(html: str, *, url: str | None = None) -> tuple[str, str] | None:
    """Return (plain text, markdown) when trafilatura finds substantive body content."""
    doc = bare_extraction(
        html,
        url=url,
        include_links=True,
        include_tables=True,
        favor_recall=True,
        output_format="python",
    )
    if not isinstance(doc, Document):
        return None

    config = use_config()
    text = determine_returnstring(
        doc,
        Extractor(
            config=config,
            output_format="txt",
            recall=True,
            links=True,
            tables=True,
        ),
    ).strip()
    if len(text) < MIN_TRAFILATURA_CHARS:
        return None

    markdown = determine_returnstring(
        doc,
        Extractor(
            config=config,
            output_format="markdown",
            recall=True,
            links=True,
            tables=True,
        ),
    ).strip()
    return text, markdown or text
