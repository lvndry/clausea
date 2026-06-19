"""canonicalize_url strips locale signals for deduplication comparison.

The function must:
- Strip known ISO 639-1 language-code path segments (/en/, /fr/, /de/, /en-US/, etc.).
- Strip locale query params (?lang=, ?locale=, ?hl=, ?language=).
- Preserve path segments that are NOT language codes (/uk/, /us/, /eu/ are regions).
- Preserve all other query params.
- Be idempotent.
"""

import pytest

from src.pipeline.helpers import canonicalize_url

# ---------------------------------------------------------------------------
# Locale path prefix stripping
# ---------------------------------------------------------------------------


def test_strips_bare_2_letter_locale_prefix():
    assert canonicalize_url("https://example.com/en/privacy") == "https://example.com/privacy"


def test_strips_ietf_locale_prefix_uppercase_region():
    assert canonicalize_url("https://example.com/en-US/terms") == "https://example.com/terms"


def test_strips_ietf_locale_prefix_lowercase_region():
    assert canonicalize_url("https://example.com/pt-br/cookies") == "https://example.com/cookies"


def test_strips_fr_locale_prefix():
    assert canonicalize_url("https://example.com/fr/privacy") == "https://example.com/privacy"


def test_strips_de_locale_prefix():
    assert canonicalize_url("https://example.com/de/agb") == "https://example.com/agb"


def test_strips_ja_locale_prefix():
    assert canonicalize_url("https://example.com/ja/policy") == "https://example.com/policy"


def test_strips_ko_locale_prefix():
    assert canonicalize_url("https://example.com/ko/terms") == "https://example.com/terms"


def test_strips_es_locale_prefix():
    assert canonicalize_url("https://example.com/es/privacy") == "https://example.com/privacy"


def test_strips_zh_locale_prefix():
    assert canonicalize_url("https://example.com/zh/privacy") == "https://example.com/privacy"


def test_strips_en_gb_locale_prefix():
    assert canonicalize_url("https://example.com/en-GB/terms") == "https://example.com/terms"


def test_strips_locale_prefix_preserves_remaining_path():
    assert (
        canonicalize_url("https://example.com/en/legal/privacy-policy")
        == "https://example.com/legal/privacy-policy"
    )


def test_strips_locale_in_middle_of_path():
    # /en/ appearing mid-path is also a locale segment and must be stripped.
    assert (
        canonicalize_url("https://example.com/help/en/privacy")
        == "https://example.com/help/privacy"
    )


# ---------------------------------------------------------------------------
# Locale query param stripping
# ---------------------------------------------------------------------------


def test_strips_lang_query_param():
    assert canonicalize_url("https://example.com/privacy?lang=en") == "https://example.com/privacy"


def test_strips_locale_query_param():
    assert canonicalize_url("https://example.com/terms?locale=en-US") == "https://example.com/terms"


def test_strips_hl_query_param():
    assert canonicalize_url("https://example.com/legal?hl=en") == "https://example.com/legal"


def test_strips_language_query_param():
    assert (
        canonicalize_url("https://example.com/privacy?language=fr") == "https://example.com/privacy"
    )


def test_strips_locale_param_preserves_other_params():
    result = canonicalize_url("https://example.com/legal?lang=en&id=42")
    assert result == "https://example.com/legal?id=42"


def test_strips_locale_param_preserves_tracker_params():
    # canonicalize_url only removes locale params, not trackers — normalize_url handles those.
    result = canonicalize_url("https://example.com/privacy?lang=en&utm_source=email")
    assert result == "https://example.com/privacy?utm_source=email"


def test_strips_both_path_and_query_locale():
    result = canonicalize_url("https://example.com/fr/privacy?lang=fr")
    assert result == "https://example.com/privacy"


# ---------------------------------------------------------------------------
# URLs that must NOT be affected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        # Full words — not 2-letter ISO codes.
        "https://example.com/english-law/privacy",
        "https://example.com/french-press/policy",
        # Region codes that are NOT in the ISO 639-1 language code list.
        "https://example.com/uk/privacy",
        "https://example.com/us/terms",
        "https://example.com/eu/policy",
        "https://example.com/au/cookies",
        # Deep path where non-locale segments surround a region code.
        "https://example.com/legal/eu/gdpr",
        # No locale at all.
        "https://example.com/privacy",
        "https://example.com/legal/terms-of-service",
        # Amazon-style identity param.
        "https://www.amazon.com/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM",
    ],
)
def test_url_unchanged(url: str):
    assert canonicalize_url(url) == url


def test_non_locale_query_params_preserved():
    url = "https://example.com/terms?id=7&section=privacy"
    assert canonicalize_url(url) == url


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/en/privacy",
        "https://example.com/en-US/terms",
        "https://example.com/fr/privacy?lang=fr",
        "https://example.com/privacy?locale=en-US",
        "https://example.com/privacy",
        "https://example.com/uk/legal",
    ],
)
def test_idempotent(url: str):
    once = canonicalize_url(url)
    twice = canonicalize_url(once)
    assert once == twice, f"Not idempotent: {url!r} → {once!r} → {twice!r}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_root_url_unchanged():
    assert canonicalize_url("https://example.com/") == "https://example.com/"


def test_locale_only_path_becomes_root():
    # /en/ with nothing after → canonical root.
    assert canonicalize_url("https://example.com/en/") == "https://example.com/"


def test_fragment_stripped():
    # Fragments are not significant for dedup.
    assert (
        canonicalize_url("https://example.com/en/privacy#section1") == "https://example.com/privacy"
    )


def test_multiple_locale_segments_stripped():
    # Pathological case: two locale segments in a row.
    result = canonicalize_url("https://example.com/en/fr/privacy")
    assert result == "https://example.com/privacy"
