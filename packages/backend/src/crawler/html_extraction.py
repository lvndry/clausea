"""HTML main-content extraction via trafilatura."""

from __future__ import annotations

import re

from trafilatura.core import bare_extraction, determine_returnstring
from trafilatura.metadata import Document
from trafilatura.settings import Extractor, use_config

MIN_TRAFILATURA_CHARS = 200


def _plain_text_from_markdown(markdown: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", markdown, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", " ", text)
    text = re.sub(r"^\s{0,3}[>#\-\*\+]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~]{1,3}", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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

    markdown = determine_returnstring(
        doc,
        Extractor(
            config=use_config(),
            output_format="markdown",
            recall=True,
            links=True,
            tables=True,
        ),
    ).strip()
    if len(markdown) < MIN_TRAFILATURA_CHARS:
        return None

    text = _plain_text_from_markdown(markdown)
    return text, markdown
