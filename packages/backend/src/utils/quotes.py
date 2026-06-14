"""Locate verbatim quotes inside source text, tolerant of whitespace and smart punctuation.

A match yields real character offsets so a quote can be highlighted ("show me where it says
that"); a fuzzy gist-only match returns no offsets and is reported unverified.
"""

import re


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def flexible_quote_regex(quote: str) -> re.Pattern[str] | None:
    """Compile a regex matching ``quote`` in the original text while tolerating whitespace
    runs and smart-quote/dash variants, so a hit yields real offsets.
    """
    tokens = [token for token in re.split(r"\s+", quote.strip()) if token]
    if not tokens:
        return None

    def char_class(ch: str) -> str:
        if ch in "'‘’`":
            return r"['‘’`]"
        if ch in '"“”':
            return r"[\"“”]"
        if ch in "-–—":
            return r"[-–—]"
        return re.escape(ch)

    body = r"\s+".join("".join(char_class(ch) for ch in token) for token in tokens)
    try:
        return re.compile(body)
    except re.error:
        return None


def resolve_quote_offsets(haystack: str, quote: str) -> tuple[int | None, int | None, bool]:
    """Return ``(start, end, verified)`` for ``quote`` within ``haystack``.

    Exact or whitespace/smart-quote-tolerant matches return real offsets and verified=True;
    a fuzzy gist-only match (long quotes) returns ``(None, None, False)``.
    """
    if not haystack or not quote:
        return None, None, False

    idx = haystack.find(quote)
    if idx != -1:
        return idx, idx + len(quote), True

    pattern = flexible_quote_regex(quote)
    if pattern is not None:
        match = pattern.search(haystack)
        if match is not None:
            return match.start(), match.end(), True

    # Fuzzy fragment match confirms the gist is present but NOT a byte-exact span:
    # report it unverified with no offsets rather than a false "verified" badge.
    if len(quote) >= 40:
        collapsed_h = collapse_ws(haystack)
        target = collapse_ws(quote)
        window = len(target) * 3 // 4
        if window >= 30:
            for i in range(len(target) - window + 1):
                if target[i : i + window] in collapsed_h:
                    return None, None, False

    return None, None, False
