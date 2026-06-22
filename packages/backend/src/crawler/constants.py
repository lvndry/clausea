"""Crawler-wide constants, compiled regexes, and locale-canonicalisation functions.

**What it contains**
- Default ``User-Agent`` and ``Accept`` header values sent on every HTTP request.
- Timeout/env-or-default integers controlling browser launch, navigation, SPA hydration, etc.
- Pre-compiled regexes for asset blocking (``_BLOCKED_ASSETS_RE``), mirror/staging subdomain
  detection (``_MIRROR_SUBDOMAIN_RE``), policy-sitemap heuristics (``_POLICY_SITEMAP_RE``),
  and consent-banner container elements (``_CONSENT_CONTAINER_RE``).
- Tracking-query-param filter set (``_TRACKING_QUERY_PARAMS``), locale-language code sets,
  and consent-banner text markers.
- ``locale_canonical_key`` and ``english_locale_canonical_key`` — URL canonicalisers that
  strip locale-path segments and locale-query params so the same document in different
  languages maps to one crawl result.

**What it prevents**
Importing magic numbers or duplicated regexes across the nine crawler submodules.
All tunable crawler parameters live here, sourced from env vars with sensible defaults.
"""

import os
import re
from urllib.parse import ParseResult, parse_qsl, urlencode, urlunparse

import tldextract

_TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())

_LOCALE_QUERY_KEYS = frozenset(
    {"l", "lang", "hl", "locale", "lr", "language", "setlang", "uselang", "ui_locale"}
)
_REDIRECT_QUERY_KEYS = frozenset(
    {
        "return_to",
        "returnto",
        "return",
        "redirect",
        "redirect_to",
        "redirect_uri",
        "redir",
        "next",
        "url",
        "continue",
        "dest",
        "destination",
        "goto",
        "go",
        "ref_url",
        "callback",
        "came_from",
        "origin",
    }
)
_LANGUAGE_CODES = frozenset(
    {
        "ar",
        "bg",
        "cs",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "fa",
        "fi",
        "fr",
        "he",
        "hi",
        "hu",
        "id",
        "it",
        "ja",
        "ko",
        "lt",
        "lv",
        "ms",
        "nl",
        "no",
        "pl",
        "pt",
        "ro",
        "ru",
        "sk",
        "sl",
        "sv",
        "th",
        "tr",
        "vi",
        "zh",
    }
)
_LANGUAGE_NAMES = frozenset(
    {
        "arabic",
        "bulgarian",
        "czech",
        "danish",
        "dutch",
        "english",
        "finnish",
        "french",
        "german",
        "greek",
        "hungarian",
        "indonesian",
        "italian",
        "japanese",
        "koreana",
        "korean",
        "norwegian",
        "polish",
        "portuguese",
        "romanian",
        "russian",
        "schinese",
        "tchinese",
        "spanish",
        "swedish",
        "thai",
        "turkish",
        "ukrainian",
        "vietnamese",
    }
)
_ENGLISH_TOKENS = frozenset({"en", "english"})

_AMBIGUOUS_LOCALE_QUERY_KEYS = frozenset({"l", "lr"})

_TRACKING_QUERY_PARAMS = frozenset(
    {
        "gclid",
        "gbraid",
        "wbraid",
        "dclid",
        "fbclid",
        "msclkid",
        "yclid",
        "twclid",
        "ttclid",
        "igshid",
        "li_fat_id",
        "rdt_cid",
        "_ga",
        "_gl",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
        "_hsenc",
        "_hsmi",
        "vero_id",
        "vero_conv",
        "oly_anon_id",
        "oly_enc_id",
        "ef_id",
        "s_kwcid",
        "rel",
    }
)

_MIRROR_SUBDOMAIN_RE = re.compile(r"(?:^|[.-])(?:internal|staging|preview)(?:$|\.)")

_POLICY_SITEMAP_RE = re.compile(
    r"legal|privacy|terms|policy|tos|gdpr|ccpa|dpa|cookie|compliance|trust",
    re.IGNORECASE,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; ClauseaBot/2.0; +https://www.clausea.co/bot.html; lvndry@proton.me)"
)

ACCEPT_HEADER = (
    "text/markdown, text/html;q=0.9, text/plain;q=0.8, application/json;q=0.7, */*;q=0.5"
)

# Stealth fallback headers used when the bot UA triggers a JS-shell bot-wall.
# Only used for the secondary static retry; the primary fetch always uses DEFAULT_USER_AGENT.
STEALTH_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
STEALTH_ACCEPT_HEADER = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)

DEFAULT_NO_POLICY_PAGE_BUDGET = int(os.getenv("CRAWLER_NO_POLICY_PAGE_BUDGET", "50"))
CONVERGENCE_LEGAL_SCORE = 0.2
CRAWL_EXHAUSTION_GRACE = int(os.getenv("CRAWLER_EXHAUSTION_GRACE", "10"))
# Abort a crawl after this many *consecutive* URL failures with no success in between.
# Fires when an entire domain is consistently inaccessible (bot wall, auth gate, etc.)
# so the job fails fast rather than exhausting the max-pages budget on dead URLs.
CRAWL_BOT_WALL_ABORT = int(os.getenv("CRAWLER_BOT_WALL_ABORT", "20"))
# Stop attempting browser renders once this many consecutive browser fetches in a single
# crawl session have failed (timeout, crash). Prevents zombie Camoufox processes from
# accumulating when pages consistently timeout in the browser.
BROWSER_DOMAIN_FAILURE_CAP = int(os.getenv("CRAWLER_BROWSER_DOMAIN_FAILURE_CAP", "3"))
MIN_PAGES_PER_SEED = int(os.getenv("CRAWLER_MIN_PAGES_PER_SEED", "60"))
MAX_ENGLISH_LOCALE_VARIANTS_PER_DOC = int(
    os.getenv("CRAWLER_MAX_ENGLISH_LOCALE_VARIANTS_PER_DOC", "2")
)
MIN_CONTENT_LENGTH_FOR_SPA_CHECK = 500
SPA_HYDRATION_RETRIES = 3
MAX_CHILD_SITEMAPS = int(os.getenv("CRAWLER_MAX_CHILD_SITEMAPS", "200"))
_MAX_GENERIC_CHILD_SITEMAPS = int(os.getenv("CRAWLER_MAX_GENERIC_CHILD_SITEMAPS", "8"))
MAX_HEADER_BYTES = 65_536
BROWSER_NAV_TIMEOUT_MS = 20_000
BROWSER_LOAD_STATE_TIMEOUT_MS = int(os.getenv("CRAWLER_BROWSER_LOAD_STATE_MS", "2000"))
BROWSER_LAUNCH_TIMEOUT_S = float(os.getenv("CRAWLER_BROWSER_LAUNCH_TIMEOUT_S", "60"))
MAX_LEGAL_SCORE_SCALE = 10.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

_BLOCKED_ASSETS_RE = re.compile(
    r"\.(?:png|jpe?g|gif|webp|avif|svg|ico|bmp|tiff?"
    r"|woff2?|ttf|otf|eot"
    r"|mp4|webm|ogg|ogv|mp3|wav|m4a|m4v|mov|avi)(?:[?#]|$)",
    re.IGNORECASE,
)

_CONSENT_CONTAINER_RE = re.compile(
    r"(onetrust|ot-sdk|ot-pc|truste|trustarc|cookiebot|osano|usercentrics|didomi|klaro|"
    r"cookie-?consent|consent-?(?:banner|manager|preference)|privacy-?(?:preference|settings)|"
    r"cmp[-_]|_shein_privacy)",
    re.IGNORECASE,
)
_CONSENT_TEXT_MARKERS = (
    "manage consent",
    "strictly necessary cookies",
    "reject all",
    "confirm my choices",
    "privacy settings center",
    "privacy preference center",
    "store or retrieve information on your browser",
)


def _english_locale_variant(token: str) -> str | None:
    if token.lower().strip() in ("en", "english"):
        return "en"
    return None


def _is_bare_language(token: str) -> bool:
    lowered = token.lower()
    if "-" in lowered or "_" in lowered:
        return False
    return lowered in _LANGUAGE_CODES or lowered in _LANGUAGE_NAMES


def _is_locale_query_value(key: str, value: str) -> bool:
    lowered = value.lower()
    if not lowered or "-" in lowered or "_" in lowered:
        return False
    if key.lower() in _AMBIGUOUS_LOCALE_QUERY_KEYS:
        return _is_bare_language(lowered)
    return lowered.isalpha()


def locale_canonical_key(parsed: ParseResult) -> tuple[str, bool, bool]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    kept_segments: list[str] = []
    had_signal = False
    is_english = False
    for seg in segments:
        if _is_bare_language(seg):
            had_signal = True
            if seg.lower() in _ENGLISH_TOKENS:
                is_english = True
            continue
        kept_segments.append(seg)

    kept_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in _LOCALE_QUERY_KEYS and _is_locale_query_value(key, value):
            had_signal = True
            if value.lower() in _ENGLISH_TOKENS:
                is_english = True
            continue
        kept_query.append((key, value))

    canonical_path = "/" + "/".join(kept_segments)
    canonical = urlunparse(
        (parsed.scheme, parsed.netloc, canonical_path, "", urlencode(kept_query), "")
    )
    return canonical, had_signal, is_english


def english_locale_canonical_key(parsed: ParseResult) -> tuple[str, str | None]:
    segments = [seg for seg in parsed.path.split("/") if seg]
    kept_segments: list[str] = []
    english_variant: str | None = None
    for seg in segments:
        variant = _english_locale_variant(seg)
        if variant is not None:
            english_variant = english_variant or variant
            continue
        kept_segments.append(seg)

    kept_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        variant = _english_locale_variant(value) if key.lower() in _LOCALE_QUERY_KEYS else None
        if variant is not None:
            english_variant = english_variant or variant
            continue
        kept_query.append((key, value))

    canonical_path = "/" + "/".join(kept_segments)
    canonical = urlunparse(
        (parsed.scheme, parsed.netloc, canonical_path, "", urlencode(kept_query), "")
    )
    return canonical, english_variant
