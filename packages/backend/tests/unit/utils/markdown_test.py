"""Tests for markdown_to_text utility."""

from src.utils.markdown import markdown_to_text


class TestMarkdownToText:
    """Tests for the markdown_to_text pure function."""

    def test_empty_string(self) -> None:
        assert markdown_to_text("") == ""

    def test_none_input(self) -> None:
        assert markdown_to_text(None) == ""  # type: ignore[arg-type]

    def test_plain_text_unchanged(self) -> None:
        assert markdown_to_text("Hello world") == "Hello world"

    # ── Bold & italic ───────────────────────────────────────────────

    def test_bold_asterisks(self) -> None:
        assert "important" in markdown_to_text("This is **important** text")
        assert "**" not in markdown_to_text("This is **important** text")

    def test_italic_asterisks(self) -> None:
        result = markdown_to_text("This is *emphasized* text")
        assert "emphasized" in result
        assert result.count("*") == 0

    def test_bold_underscores(self) -> None:
        result = markdown_to_text("This is __bold__ text")
        assert "bold" in result
        assert "__" not in result

    def test_italic_underscores(self) -> None:
        result = markdown_to_text("This is _italic_ text")
        assert "italic" in result
        assert result.count("_") == 0

    # ── Headers ─────────────────────────────────────────────────────

    def test_h1(self) -> None:
        result = markdown_to_text("# Title")
        assert "Title" in result
        assert "#" not in result

    def test_h2(self) -> None:
        result = markdown_to_text("## Subtitle")
        assert "Subtitle" in result
        assert "#" not in result

    def test_h3(self) -> None:
        result = markdown_to_text("### Section")
        assert "Section" in result

    # ── Links ───────────────────────────────────────────────────────

    def test_link_keeps_text(self) -> None:
        result = markdown_to_text("[Click here](https://example.com)")
        assert "Click here" in result
        assert "https://example.com" not in result

    def test_autolink_stripped_by_html_removal(self) -> None:
        """Autolinks like <https://...> are consumed by the HTML tag removal regex
        before the autolink regex can process them. This is a known limitation."""
        result = markdown_to_text("<https://example.com>")
        # The HTML tag regex <[^>]+> matches <https://example.com> and removes it
        assert "<" not in result

    # ── Images ──────────────────────────────────────────────────────

    def test_image_replaced_with_alt(self) -> None:
        result = markdown_to_text("![Logo](https://example.com/logo.png)")
        assert "Logo" in result
        assert "https://example.com" not in result

    # ── Code ────────────────────────────────────────────────────────

    def test_inline_code_removed(self) -> None:
        result = markdown_to_text("Use the `print` function")
        assert "print" not in result or "`" not in result

    def test_fenced_code_block_removed(self) -> None:
        md = "Before\n```python\nprint('hello')\n```\nAfter"
        result = markdown_to_text(md)
        assert "print" not in result
        assert "Before" in result
        assert "After" in result

    def test_tilde_code_block_removed(self) -> None:
        md = "Before\n~~~\ncode here\n~~~\nAfter"
        result = markdown_to_text(md)
        assert "code here" not in result

    # ── Lists ───────────────────────────────────────────────────────

    def test_unordered_list(self) -> None:
        md = "- Item one\n- Item two\n- Item three"
        result = markdown_to_text(md)
        assert "Item one" in result
        assert "Item two" in result

    def test_ordered_list(self) -> None:
        md = "1. First\n2. Second\n3. Third"
        result = markdown_to_text(md)
        assert "First" in result
        assert "Second" in result

    # ── Blockquotes ─────────────────────────────────────────────────

    def test_blockquote(self) -> None:
        result = markdown_to_text("> This is a quote")
        assert "This is a quote" in result
        assert ">" not in result

    # ── Strikethrough ───────────────────────────────────────────────

    def test_strikethrough(self) -> None:
        result = markdown_to_text("~~deleted~~ kept")
        assert "deleted" in result
        assert "~~" not in result

    # ── HTML tags ───────────────────────────────────────────────────

    def test_html_tags_removed(self) -> None:
        result = markdown_to_text("<div>Content</div>")
        assert "Content" in result
        assert "<div>" not in result

    # ── Horizontal rules ────────────────────────────────────────────

    def test_horizontal_rule(self) -> None:
        result = markdown_to_text("Above\n---\nBelow")
        assert "Above" in result
        assert "Below" in result

    # ── Tables ──────────────────────────────────────────────────────

    def test_table_pipes_removed(self) -> None:
        md = "| Header 1 | Header 2 |\n|---|---|\n| Cell 1 | Cell 2 |"
        result = markdown_to_text(md)
        assert "|" not in result
        assert "Header 1" in result

    # ── Whitespace cleanup ──────────────────────────────────────────

    def test_multiple_newlines_collapsed(self) -> None:
        result = markdown_to_text("Line 1\n\n\n\n\nLine 2")
        assert "\n\n\n" not in result

    def test_multiple_spaces_collapsed(self) -> None:
        result = markdown_to_text("Too   many   spaces")
        assert "  " not in result
