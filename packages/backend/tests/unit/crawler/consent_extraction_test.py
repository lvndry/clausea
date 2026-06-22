"""Guards content extraction against consent/cookie widgets winning over the real body.

A consent widget's class often contains "privacy", so a `[class*=privacy]` selector latched
onto a ~2.8k-char OneTrust/Shein consent block and discarded the ~48k real policy. These tests
assert the real body wins, clean pages are unchanged, and a genuine Cookie Policy is preserved.
"""

from bs4 import BeautifulSoup

from src.crawler import ClauseaCrawler

REAL_POLICY = (
    "Privacy Policy. We collect personal data including your name and email. "
    "The information we collect is used to provide the service. We share information with "
    "third parties. You have rights to access and delete your data. Retention periods apply. "
) * 6

CONSENT_WIDGET = (
    "Privacy settings center. Manage Consent Preferences. Strictly Necessary Cookies. "
    "Reject All. Confirm My Choices. Store or retrieve information on your browser."
)


def _text(html: str) -> str:
    crawler = ClauseaCrawler()
    return (
        crawler._extract_main_content_soup(BeautifulSoup(html, "html.parser"))
        .get_text(" ", strip=True)
        .lower()
    )


def test_real_body_wins_over_consent_widget() -> None:
    # Consent block carries a privacy-ish class; real body sits in a plain #app with no
    # recognized content class — exactly the Shein shape that returned only the widget.
    html = f"""
    <html><body>
      <div class="_shein_privacy_preference cmp_c_1200">{CONSENT_WIDGET}</div>
      <div id="app"><div id="in-app">{REAL_POLICY}</div></div>
    </body></html>
    """
    text = _text(html)
    assert "we collect personal data" in text
    assert "reject all" not in text
    assert "strictly necessary cookies" not in text


def test_clean_page_without_consent_is_unchanged() -> None:
    html = f"<html><body><main>{REAL_POLICY}</main></body></html>"
    text = _text(html)
    assert "we collect personal data" in text
    assert "your data" in text


def test_consent_class_with_real_prose_is_preserved() -> None:
    # Class matches the consent-vendor regex (privacy-settings) but the text is real policy
    # prose with no widget controls (<2 markers) — the text corroboration must keep it.
    prose = (
        "This page explains how we use cookies and similar technologies to recognise you. "
        "We collect personal data via cookies. You have rights regarding this information "
        "and its retention. We share information with third parties. "
    ) * 5
    html = f'<html><body><div class="privacy-settings-doc">{prose}</div></body></html>'
    text = _text(html)
    assert "we collect personal data via cookies" in text
