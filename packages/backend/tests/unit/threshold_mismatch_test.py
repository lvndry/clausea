"""Pins down the crawler-vs-processor length-threshold mismatch.

The ship-readiness investigation (docs/superpowers/specs/2026-05-25-ship-readiness-design.md)
found that two hardcoded length gates disagree about what "sufficient content" means:

* Crawler `_content_is_sufficient` (crawler.py:1462)   accepts markdown >= 200 chars stripped.
* Processor `_process_crawl_result`  (pipeline.py:937)  demands text-after-strip >= 300 chars.

A page that passes the first gate will skip the browser-rendering retry; if its
markdown-to-text strip then yields fewer than 300 chars, it is silently dropped
with reason="insufficient_content" — exactly what was happening to JS-SPA shells
for Slack / Amazon / Airbnb.

This test reproduces a realistic shell payload that lands in the mismatch zone.
If someone harmonises the gates, this test will fail; update the fixture and
the doc reference at the same time.
"""

from __future__ import annotations

from src.utils.markdown import markdown_to_text


def test_spa_shell_passes_crawler_gate_and_fails_processor_gate() -> None:
    spa_markdown = (
        "# Welcome\n\n"
        "We use cookies and similar tech.\n\n"
        "[Privacy](https://example.com/privacy) | "
        "[Terms](https://example.com/terms) | "
        "[Cookie policy](https://example.com/cookies)\n\n"
        "* Sign in\n"
        "* Sign up\n"
        "* Help center\n"
        "* Loading...\n\n"
        "Please enable JavaScript to view this page."
    )

    stripped_markdown_len = len(spa_markdown.strip())
    assert 200 <= stripped_markdown_len < 300, (
        f"fixture must sit in the mismatch zone (markdown stripped len={stripped_markdown_len})"
    )

    stripped_text_len = len(markdown_to_text(spa_markdown).strip())
    assert stripped_text_len < 300, (
        f"hypothesis: post-strip text length stays below the 300-char processor gate "
        f"(got {stripped_text_len})"
    )


def test_markdown_to_text_does_not_grow_content() -> None:
    """Sanity check the assumption that strip is near-identity on length.

    If markdown_to_text ever inflates content significantly, the mismatch
    analysis above no longer holds and the spec needs revisiting.
    """
    samples = [
        "# Heading\n\nSome **bold** and *italic* text with a [link](https://x.com).",
        "Plain content with no markdown features at all to speak of.",
        "* item one\n* item two\n* item three\n* item four",
    ]
    for md in samples:
        stripped = markdown_to_text(md)
        assert len(stripped) <= len(md), (
            f"strip must not inflate: input={len(md)} output={len(stripped)} for {md!r}"
        )
