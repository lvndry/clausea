"""canonicalize_url strips locale signals for deduplication comparison.

The function must:
- Strip bare ISO 639-1 2-letter language-code path segments (/en/, /fr/, /de/)
  but NOT IETF regional tags (/en-US/, /pt-BR/, /en-GB/) — region subtags encode
  legal jurisdiction and must be preserved as separate documents.
- Strip display-language-only query params (?lang=, ?hl=, ?language=).
- NOT strip ?locale= params — these frequently encode jurisdiction, not just language.
- Preserve region/jurisdiction path segments (/us/, /uk/, /eu/, /eea/, /row/).
- Preserve all other query params.
- Be idempotent.
"""

import pytest

from src.pipeline.helpers import canonicalize_url

# ---------------------------------------------------------------------------
# Bare language code path prefix stripping (safe — no region component)
# ---------------------------------------------------------------------------


def test_strips_bare_2_letter_locale_prefix():
    assert canonicalize_url("https://example.com/en/privacy") == "https://example.com/privacy"


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
# IETF regional tags MUST be preserved (region encodes legal jurisdiction)
# ---------------------------------------------------------------------------


def test_preserves_ietf_regional_tag_en_us():
    # en-US may carry CCPA obligations that are legally distinct from en-GB (GDPR).
    assert canonicalize_url("https://example.com/en-US/terms") == "https://example.com/en-US/terms"


def test_preserves_ietf_regional_tag_pt_br():
    # pt-BR (Brazilian law) and pt-PT (EU law) are legally distinct documents.
    assert (
        canonicalize_url("https://example.com/pt-BR/cookies") == "https://example.com/pt-BR/cookies"
    )


def test_preserves_ietf_regional_tag_pt_br_lowercase():
    assert (
        canonicalize_url("https://example.com/pt-br/cookies") == "https://example.com/pt-br/cookies"
    )


def test_preserves_ietf_regional_tag_en_gb():
    # en-GB may have materially different arbitration clauses and governing law.
    assert canonicalize_url("https://example.com/en-GB/terms") == "https://example.com/en-GB/terms"


def test_preserves_zh_not_in_allowlist():
    # zh is omitted from the safe-to-strip allowlist because zh-CN vs zh-TW are
    # legally distinct jurisdictions (Mainland China vs Taiwan).
    assert canonicalize_url("https://example.com/zh/privacy") == "https://example.com/zh/privacy"


# ---------------------------------------------------------------------------
# Jurisdiction / region path segments must be preserved
# ---------------------------------------------------------------------------


def test_preserves_eea_jurisdiction_path():
    # /eea/ is a jurisdiction segment (GDPR scope), not a display-language code.
    url = "https://example.com/eea/privacy-policy"
    assert canonicalize_url(url) == url


def test_preserves_us_jurisdiction_path():
    # /us/ is a geographic region identifier, not a language code.
    url = "https://example.com/us/privacy-policy"
    assert canonicalize_url(url) == url


def test_preserves_row_jurisdiction_path():
    url = "https://example.com/row/terms"
    assert canonicalize_url(url) == url


def test_eea_and_us_remain_distinct_documents():
    # GDPR-scoped and CCPA-scoped variants must NOT collapse to the same canonical URL.
    assert canonicalize_url("https://example.com/eea/privacy-policy") != canonicalize_url(
        "https://example.com/us/privacy-policy"
    )


def test_en_us_and_en_gb_remain_distinct_documents():
    # Jurisdiction-specific variants must survive canonicalization as separate documents.
    assert canonicalize_url("https://example.com/en-US/terms") != canonicalize_url(
        "https://example.com/en-GB/terms"
    )


# ---------------------------------------------------------------------------
# Locale query param stripping
# ---------------------------------------------------------------------------


def test_strips_lang_query_param():
    assert canonicalize_url("https://example.com/privacy?lang=en") == "https://example.com/privacy"


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
# ?locale= must NOT be stripped (encodes jurisdiction, not just display language)
# ---------------------------------------------------------------------------


def test_preserves_locale_query_param():
    # ?locale= can encode legal jurisdiction (GDPR vs CCPA variant selection).
    url = "https://example.com/terms?locale=en-US"
    assert canonicalize_url(url) == url


def test_preserves_locale_query_param_alongside_other_params():
    result = canonicalize_url("https://example.com/legal?locale=en-US&id=42")
    assert result == "https://example.com/legal?locale=en-US&id=42"


# ---------------------------------------------------------------------------
# URLs that must NOT be affected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        # Full words — not 2-letter ISO codes.
        "https://example.com/english-law/privacy",
        "https://example.com/french-press/policy",
        # Region codes not in the ISO 639-1 language code allowlist.
        "https://example.com/uk/privacy",
        "https://example.com/us/terms",
        "https://example.com/eu/policy",
        "https://example.com/au/cookies",
        # IETF regional tags preserved (region = jurisdiction).
        "https://example.com/en-US/terms",
        "https://example.com/pt-BR/cookies",
        "https://example.com/en-GB/legal",
        "https://example.com/zh-CN/privacy",
        "https://example.com/zh-TW/privacy",
        # Bare language code not in the safe-to-strip allowlist.
        "https://example.com/zh/privacy",
        # Jurisdiction segments in deeper paths.
        "https://example.com/legal/eu/gdpr",
        "https://example.com/eea/privacy-policy",
        "https://example.com/row/terms",
        # ?locale= preserved.
        "https://example.com/terms?locale=en-US",
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
        "https://example.com/eea/privacy-policy",
        "https://example.com/zh/privacy",
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
