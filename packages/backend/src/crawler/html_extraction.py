"""HTML main-content extraction via trafilatura."""

from __future__ import annotations

import trafilatura

MIN_TRAFILATURA_CHARS = 200


def extract_with_trafilatura(html: str, *, url: str | None = None) -> tuple[str, str] | None:
    """Return (plain text, markdown) when trafilatura finds substantive body content."""
    text = trafilatura.extract(
        html,
        url=url,
        include_links=True,
        include_tables=True,
        favor_recall=True,
    )
    if not text or len(text.strip()) < MIN_TRAFILATURA_CHARS:
        return None

    markdown = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        favor_recall=True,
    )
    return text.strip(), (markdown or text).strip()
