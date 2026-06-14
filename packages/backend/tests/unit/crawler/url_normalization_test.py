"""normalize_url strips known tracking params but never content-bearing ones.

Tracking params (utm_*, gclid, fbclid, rel, …) never change the document, so
collapsing them avoids redundant fetches of the same page. Content-bearing
params MUST be preserved — language can proxy region (en→US TOS, fr→EU TOS),
and identity params carry the document itself (Amazon: display.html?nodeId=…).
"""

from src.crawler import ClauseaCrawler


def _norm(url: str) -> str:
    return ClauseaCrawler(respect_robots_txt=False).normalize_url(url)


def test_strips_utm_and_click_trackers():
    assert (
        _norm("https://x.com/a?utm_source=g&utm_medium=email&utm_campaign=spring")
        == "https://x.com/a"
    )
    assert _norm("https://x.com/a?gclid=abc") == "https://x.com/a"
    assert _norm("https://x.com/a?fbclid=abc&msclkid=def") == "https://x.com/a"
    assert _norm("https://x.com/a?rel=footer") == "https://x.com/a"


def test_strips_trackers_but_keeps_content_params():
    # Tracker removed, identity param kept.
    assert (
        _norm(
            "https://www.amazon.com/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM&utm_source=nl"
        )
        == "https://www.amazon.com/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM"
    )


def test_never_strips_language_or_identity_params():
    # language may proxy region — must be preserved.
    assert _norm("https://x.com/privacy?language=fr") == "https://x.com/privacy?language=fr"
    assert _norm("https://x.com/d?id=42") == "https://x.com/d?id=42"
    assert _norm("https://x.com/d?nodeId=ABC") == "https://x.com/d?nodeId=ABC"
    assert _norm("https://x.com/explore/x?page=2") == "https://x.com/explore/x?page=2"


def test_preserves_remaining_param_order_after_stripping():
    assert (
        _norm("https://x.com/d?language=fr&utm_source=g&id=7") == "https://x.com/d?language=fr&id=7"
    )


def test_no_query_left_drops_question_mark():
    assert _norm("https://x.com/a?utm_source=g") == "https://x.com/a"


def test_fragment_still_removed():
    assert _norm("https://x.com/a?id=1#section") == "https://x.com/a?id=1"
