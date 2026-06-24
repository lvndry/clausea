"""Brand-name extraction: slug affinity, descriptive filter, suffix cleaning, title fallback."""

from src.crawler.models import CrawlResult
from src.pipeline.pipeline import (
    _clean_brand_name,
    _domain_root,
    _extract_brand_name,
    _has_affinity,
    _has_strict_slug_affinity,
    _is_valid_brand_name,
)


def _result(
    url: str, metadata: dict | None = None, title: str = "", success: bool = True
) -> CrawlResult:
    return CrawlResult(
        url=url,
        title=title,
        content="",
        markdown="",
        metadata=metadata or {},
        status_code=200 if success else 0,
        success=success,
    )


def test_domain_root_strips_subdomain_and_tld() -> None:
    assert _domain_root("netflix.com") == "netflix"
    assert _domain_root("help.netflix.com") == "netflix"
    assert _domain_root("www.23andme.com") == "23andme"
    assert _domain_root("https://bsky.app/path") == "bsky"
    assert _domain_root("open-ai.com") == "open-ai"


def test_strict_slug_affinity_matches_abbreviations() -> None:
    assert _has_strict_slug_affinity("Bluesky", "bsky") is True
    assert _has_strict_slug_affinity("Google Meet", "gmeet") is True
    assert _has_strict_slug_affinity("23andMe", "23andme") is True


def test_strict_slug_affinity_rejects_parent_domain_names() -> None:
    assert _has_strict_slug_affinity("Google Cloud", "gemini") is False
    assert _has_strict_slug_affinity("Help Center", "netflix") is False


def test_lenient_affinity_keeps_brand_that_differs_from_slug() -> None:
    assert _has_affinity("xAI", "grok", ["x.ai"]) is True


def test_lenient_affinity_rejects_unrelated_name() -> None:
    assert _has_affinity("Microsoft 365", "minecraft", ["minecraft.net"]) is False


def test_clean_strips_section_and_corporate_suffixes() -> None:
    assert _clean_brand_name("23andMe Blog") == "23andMe"
    assert _clean_brand_name("Apple Legal") == "Apple"
    assert _clean_brand_name("SHEIN Group") == "SHEIN"
    assert _clean_brand_name("Transparency Center") == ""
    assert _clean_brand_name("Help Center") == ""


def test_clean_strips_separator_delimited_section_segments() -> None:
    assert _clean_brand_name("Figma Learn - Help Center") == "Figma"


def test_clean_preserves_tld_brands_and_strips_trademarks() -> None:
    assert _clean_brand_name("character.ai blog") == "character.ai"
    assert _clean_brand_name("Peloton®") == "Peloton"


def test_validity_rejects_placeholders_dates_and_urls() -> None:
    assert _is_valid_brand_name("Netflix") is True
    assert _is_valid_brand_name("Help Center") is False
    assert _is_valid_brand_name("Aug 2022") is False
    assert _is_valid_brand_name("https://x.com") is False
    assert _is_valid_brand_name("GB") is False


def test_plurality_og_site_name_wins_and_is_cleaned() -> None:
    results = [
        _result("https://23andme.com/blog", metadata={"og:site_name": "23andMe Blog"}),
        _result("https://23andme.com/legal", metadata={"og:site_name": "23andMe Blog"}),
        _result("https://23andme.com/privacy", metadata={"og:site_name": "23andMe Blog"}),
    ]
    assert _extract_brand_name(results, "23andme", ["23andme.com"]) == "23andMe"


def test_section_name_without_affinity_is_rejected() -> None:
    results = [_result("https://netflix.com", metadata={"og:site_name": "Help Center"})]
    assert _extract_brand_name(results, "netflix", ["netflix.com"]) is None


def test_bsky_improved_to_bluesky() -> None:
    results = [
        _result("https://bsky.app", metadata={"og:site_name": "Bluesky"}),
        _result("https://bsky.app/about", metadata={"og:site_name": "Bluesky"}),
    ]
    assert _extract_brand_name(results, "bsky", ["bsky.app"]) == "Bluesky"


def test_parent_domain_google_cloud_rejected_for_gemini() -> None:
    results = [_result("https://gemini.google.com", metadata={"og:site_name": "Google Cloud"})]
    assert _extract_brand_name(results, "gemini", ["gemini.google.com"]) is None


def test_descriptive_phrase_rejected_keeps_domain_name() -> None:
    results = [
        _result(
            "https://facebook.com", metadata={"og:site_name": "Manage your privacy on Facebook"}
        )
    ]
    assert _extract_brand_name(results, "facebook", ["facebook.com"]) is None


def test_four_word_policy_title_rejected() -> None:
    results = [
        _result("https://maps.google.com", metadata={"og:site_name": "Google Meet Acceptable Use"})
    ]
    assert _extract_brand_name(results, "gmaps", ["maps.google.com"]) is None


def test_two_word_brand_kept() -> None:
    results = [_result("https://meet.google.com", metadata={"og:site_name": "Google Meet"})]
    assert _extract_brand_name(results, "gmeet", ["meet.google.com"]) == "Google Meet"


def test_failed_results_are_ignored() -> None:
    results = [
        _result("https://netflix.com", metadata={"og:site_name": "Help Center"}, success=False),
        _result("https://netflix.com", metadata={"og:site_name": "Netflix"}),
    ]
    assert _extract_brand_name(results, "netflix", ["netflix.com"]) == "Netflix"


def test_title_fallback_prefers_last_brand_segment() -> None:
    results = [_result("https://spotify.com", title="Terms and Conditions of Use - Spotify")]
    assert _extract_brand_name(results, "spotify", ["spotify.com"]) == "Spotify"


def test_title_fallback_rejects_tagline_without_affinity() -> None:
    results = [
        _result("https://shein.com", title="Women's & Men's Clothing, Shop Online Fashion | SHEIN")
    ]
    assert _extract_brand_name(results, "shein", ["shein.com"]) == "SHEIN"


def test_title_with_no_brand_segment_returns_none() -> None:
    results = [_result("https://resend.com", title="Aug 2022")]
    assert _extract_brand_name(results, "resend", ["resend.com"]) is None


def test_title_application_card_rejected_for_github() -> None:
    results = [_result("https://github.com", title="Application card")]
    assert _extract_brand_name(results, "github", ["github.com"]) is None


def test_empty_results_returns_none() -> None:
    assert _extract_brand_name([], "netflix", ["netflix.com"]) is None
