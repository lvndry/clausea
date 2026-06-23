"""Unit tests for the needs_browser_fallback heuristic.

These tests exercise the standalone helper function in isolation — no network,
no browser, no full crawler setup required.
"""

from src.crawler import StaticFetchResult, needs_browser_fallback, static_response_body_too_small
from src.crawler.constants import MIN_CONTENT_LENGTH_FOR_SPA_CHECK, MIN_STATIC_RESPONSE_BYTES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw(
    *,
    status_code: int = 200,
    content_type: str = "text/html; charset=utf-8",
    body: str = "",
    headers: dict[str, str] | None = None,
) -> StaticFetchResult:
    return StaticFetchResult(
        url="https://example.com/privacy",
        status_code=status_code,
        content_type=content_type,
        body=body,
        headers=headers or {},
    )


_RICH_HTML = """<html>
<head><title>Privacy Policy</title></head>
<body><main>
<h1>Privacy Policy</h1>
<p>{}</p>
</main></body>
</html>""".format("We collect personal information to provide and improve our services. " * 15)

_SPA_ROOT_EMPTY = """<html>
<head><title>App</title></head>
<body><div id="root"></div></body>
</html>"""

_SPA_NEXT_EMPTY = """<html>
<head><title>App</title></head>
<body><div id="__next"><div></div></div></body>
</html>"""

_SPA_APP_MINIMAL = """<html>
<head><title>App</title></head>
<body><div id="app">Loading…</div></body>
</html>"""

_SPA_ROOT_RICH = """<html>
<head><title>Privacy</title></head>
<body>
<div id="root">
<h1>Privacy Policy</h1>
<p>{}</p>
</div>
</body>
</html>""".format("We process your personal data carefully to deliver our services. " * 12)


# ---------------------------------------------------------------------------
# HTTP status codes
# ---------------------------------------------------------------------------


class TestStatusCodes:
    def test_429_never_triggers_fallback(self):
        """429 is a rate-limit hard block; browser cannot bypass it."""
        assert needs_browser_fallback(_raw(status_code=429)) is False

    def test_200_ok_with_good_content_no_fallback(self):
        assert needs_browser_fallback(_raw(status_code=200, body=_RICH_HTML)) is False

    def test_403_triggers_fallback(self):
        assert needs_browser_fallback(_raw(status_code=403)) is True

    def test_401_triggers_fallback(self):
        assert needs_browser_fallback(_raw(status_code=401)) is True

    def test_406_triggers_fallback(self):
        assert needs_browser_fallback(_raw(status_code=406, content_type="")) is True

    def test_404_triggers_fallback(self):
        """404 would trigger the function — handled upstream before this is called."""
        assert needs_browser_fallback(_raw(status_code=404)) is True

    def test_5xx_with_rich_content_no_fallback(self):
        """A 5xx response that still contains a full HTML page is usable as-is."""
        assert needs_browser_fallback(_raw(status_code=500, body=_RICH_HTML)) is False

    def test_5xx_empty_body_triggers_fallback(self):
        """A 5xx response with an empty body has no visible text → browser may help."""
        assert needs_browser_fallback(_raw(status_code=500, body="")) is True


# ---------------------------------------------------------------------------
# Content-Type checks
# ---------------------------------------------------------------------------


class TestContentType:
    def test_json_content_type_triggers_fallback(self):
        raw = _raw(content_type="application/json", body='{"status":"ok"}')
        assert needs_browser_fallback(raw) is True

    def test_empty_content_type_triggers_fallback(self):
        assert needs_browser_fallback(_raw(content_type="", body="")) is True

    def test_image_content_type_triggers_fallback(self):
        assert needs_browser_fallback(_raw(content_type="image/png", body="")) is True

    def test_html_with_charset_param_recognised(self):
        """Content-Type with a charset suffix must still be treated as HTML."""
        assert (
            needs_browser_fallback(_raw(content_type="text/html; charset=utf-8", body=_RICH_HTML))
            is False
        )

    def test_text_plain_recognised(self):
        long_text = "Privacy Policy.\n" + "We collect your data. " * 30
        assert len(long_text) >= MIN_CONTENT_LENGTH_FOR_SPA_CHECK
        raw = _raw(content_type="text/plain", body=long_text)
        assert needs_browser_fallback(raw) is False

    def test_text_markdown_recognised(self):
        md = "# Privacy Policy\n\n" + "We process your data carefully. " * 20
        assert len(md) >= MIN_CONTENT_LENGTH_FOR_SPA_CHECK
        raw = _raw(content_type="text/markdown", body=md)
        assert needs_browser_fallback(raw) is False


# ---------------------------------------------------------------------------
# SPA skeleton detection
# ---------------------------------------------------------------------------


class TestSpaSkeletonDetection:
    def test_empty_root_div_triggers_fallback(self):
        raw = _raw(body=_SPA_ROOT_EMPTY)
        assert needs_browser_fallback(raw) is True

    def test_empty_next_div_triggers_fallback(self):
        raw = _raw(body=_SPA_NEXT_EMPTY)
        assert needs_browser_fallback(raw) is True

    def test_minimal_app_div_triggers_fallback(self):
        raw = _raw(body=_SPA_APP_MINIMAL)
        assert needs_browser_fallback(raw) is True

    def test_root_div_with_rich_content_no_fallback(self):
        """div#root containing enough text should NOT trigger browser fallback."""
        raw = _raw(body=_SPA_ROOT_RICH)
        assert needs_browser_fallback(raw) is False


# ---------------------------------------------------------------------------
# Visible-text length check
# ---------------------------------------------------------------------------


class TestVisibleTextLength:
    def test_very_short_html_triggers_fallback(self):
        short = "<html><body>Loading...</body></html>"
        raw = _raw(body=short)
        assert needs_browser_fallback(raw) is True

    def test_html_above_threshold_no_fallback(self):
        assert needs_browser_fallback(_raw(body=_RICH_HTML)) is False

    def test_plain_text_below_threshold_triggers_fallback(self):
        raw = _raw(content_type="text/plain", body="hi")
        assert needs_browser_fallback(raw) is True

    def test_plain_text_above_threshold_no_fallback(self):
        body = "We process your data. " * 30
        assert len(body) >= MIN_CONTENT_LENGTH_FOR_SPA_CHECK
        raw = _raw(content_type="text/plain", body=body)
        assert needs_browser_fallback(raw) is False

    def test_script_tags_excluded_from_text_count(self):
        """Inline scripts must not inflate the visible-text counter."""
        big_payload = "a" * 2000
        html_with_scripts = (
            "<html><body>"
            f"<script>window.__DATA__ = {{}}; var x = '{big_payload}';</script>"
            "<div>Hi</div>"
            "</body></html>"
        )
        raw = _raw(body=html_with_scripts)
        # Despite the large script payload, visible text is tiny → fallback needed
        assert needs_browser_fallback(raw) is True


class TestStaticResponseBodySize:
    def test_empty_body_with_zero_content_length(self):
        raw = _raw(body="", headers={"Content-Length": "0"})
        assert static_response_body_too_small(raw) is True
        assert needs_browser_fallback(raw) is True

    def test_body_above_threshold_no_force(self):
        body = "a" * (MIN_STATIC_RESPONSE_BYTES + 50)
        raw = _raw(body=body)
        assert static_response_body_too_small(raw) is False

    def test_small_body_below_threshold(self):
        raw = _raw(body="<html><body></body></html>")
        assert len(raw.body.encode()) < MIN_STATIC_RESPONSE_BYTES
        assert static_response_body_too_small(raw) is True
