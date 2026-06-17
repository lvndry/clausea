"""Pure-translation URL variants are deduped; English locale variants are capped.

Sites like Steam (``?l=ukrainian`` over a path-locale matrix) and Epic (``?lang=…``)
expose the same legal document in dozens of translations. Each one browser-renders and
times out, so a single crawl burned ~30 min on hundreds of redundant fetches. We keep
the canonical/English variant and skip the rest. English region variants are capped
to representative coverage, while jurisdictional region paths (e.g. /eu vs /us)
remain distinct.
"""

from urllib.parse import urlparse

from src.crawler import ClauseaCrawler, locale_canonical_key


def _crawler() -> ClauseaCrawler:
    return ClauseaCrawler(allowed_domains=None, follow_external_links=False)


def test_canonical_key_strips_language_query_param() -> None:
    key, had_signal, is_english = locale_canonical_key(
        urlparse("https://store.steampowered.com/privacy_agreement?l=ukrainian")
    )
    assert key == "https://store.steampowered.com/privacy_agreement"
    assert had_signal is True
    assert is_english is False


def test_canonical_key_strips_bare_language_path_segment() -> None:
    key, had_signal, _ = locale_canonical_key(
        urlparse("https://store.steampowered.com/privacy_agreement/german")
    )
    assert key == "https://store.steampowered.com/privacy_agreement"
    assert had_signal is True


def test_canonical_key_preserves_region_qualified_locale() -> None:
    # en-GB vs en-US can differ legally — must NOT collapse.
    key, had_signal, _ = locale_canonical_key(urlparse("https://example.com/privacy/en-GB"))
    assert key == "https://example.com/privacy/en-GB"
    assert had_signal is False


def test_translation_variants_collapse_to_one_crawl() -> None:
    crawler = _crawler()
    base = "https://store.steampowered.com/privacy_agreement"
    # Canonical (language-less) admitted first.
    assert crawler.should_crawl_url(base, base, 1) is True
    # Every translation of the same agreement is now skipped.
    assert crawler.should_crawl_url(base + "/german?l=ukrainian", base, 1) is False
    assert crawler.should_crawl_url(base + "/italian?l=french", base, 1) is False


def test_region_variants_are_each_crawled() -> None:
    crawler = _crawler()
    base = "https://example.com/privacy"
    assert crawler.should_crawl_url(base + "/eu", base, 1) is True
    assert crawler.should_crawl_url(base + "/us", base, 1) is True
    assert crawler.should_crawl_url(base + "/en-GB", base, 1) is True


def test_english_region_variants_are_each_crawled() -> None:
    # en-us (CCPA), en-gb (GDPR), en-au are jurisdiction-distinct legal texts, not translations:
    # never collapsed pre-fetch. Identical ones are dropped later by the content fingerprint.
    crawler = _crawler()
    base = "https://example.com/privacy"
    assert crawler.should_crawl_url(base + "/en-us", base, 1) is True
    assert crawler.should_crawl_url(base + "/en-gb", base, 1) is True
    assert crawler.should_crawl_url(base + "/en-au", base, 1) is True


def test_english_region_query_variants_are_each_crawled() -> None:
    crawler = _crawler()
    base = "https://legal.example.com/terms"
    assert crawler.should_crawl_url(base + "?lang=en-gb", base, 1) is True
    assert crawler.should_crawl_url(base + "?lang=en-ca", base, 1) is True
    assert crawler.should_crawl_url(base + "?lang=en-au", base, 1) is True


def test_hr_and_uk_path_segments_are_not_treated_as_languages() -> None:
    # /hr/ = HR/employee policy, /uk/ = UK-GDPR region — legally distinct, never collapse.
    for region in ("hr", "uk"):
        key, had_signal, _ = locale_canonical_key(urlparse(f"https://example.com/{region}/privacy"))
        assert key == f"https://example.com/{region}/privacy"
        assert had_signal is False


def test_english_variant_kept_over_other_translations() -> None:
    crawler = _crawler()
    base = "https://legal.epicgames.com/parental-consent"
    # English admitted, registering the canonical key.
    assert crawler.should_crawl_url(base + "?lang=en", base, 1) is True
    # A non-English sibling is then a redundant translation.
    assert crawler.should_crawl_url(base + "?lang=fr", base, 1) is False
