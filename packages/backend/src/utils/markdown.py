import re


def markdown_to_text(md: str) -> str:
    """Convert markdown to clean text while preserving some structure."""
    if not md:
        return ""

    text = md

    # Remove HTML tags (common in markdown)
    text = re.sub(r"<[^>]+>", "", text)

    # Remove code blocks (both fenced and indented)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"~~~.*?~~~", "", text, flags=re.DOTALL)  # Alternative fenced blocks
    text = re.sub(r"`[^`\n]*`", "", text)  # Inline code (don't span lines)

    # Remove indented code blocks (4+ spaces at start of line)
    text = re.sub(r"^(    |\t).*$", "", text, flags=re.MULTILINE)

    # Convert headers to plain text with extra spacing
    text = re.sub(r"^#{1,6}\s*(.+?)(?:\s*#+)?$", r"\1\n", text, flags=re.MULTILINE)

    # Handle strikethrough
    text = re.sub(r"~~([^~]+)~~", r"\1", text)

    # Remove markdown formatting but preserve text
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)  # Bold
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)  # Italic (non-greedy)
    text = re.sub(r"__([^_\n]+)__", r"\1", text)  # Bold alt
    text = re.sub(r"_([^_\n]+)_", r"\1", text)  # Italic alt

    # Handle links - keep the text, remove URL
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)  # Auto-links

    # Handle images - remove entirely or keep alt text
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"[Image: \1]", text)

    # Clean up lists - preserve hierarchy with indentation
    text = re.sub(r"^(\s*)[-*+]\s+", r"\1• ", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)\d+\.\s+", r"\1", text, flags=re.MULTILINE)

    # Handle blockquotes
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)

    # Handle horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "---", text, flags=re.MULTILINE)

    # Handle tables - this is basic, just remove pipe separators
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"^[-:\s|]+$", "", text, flags=re.MULTILINE)  # Remove table separator rows

    # Clean up whitespace more carefully
    text = re.sub(r"\n{3,}", "\n\n", text)  # Multiple newlines to double
    text = re.sub(r"[ \t]+", " ", text)  # Multiple spaces/tabs to single space
    text = re.sub(r"[ \t]*\n", "\n", text)  # Remove trailing spaces before newlines

    return text.strip()
