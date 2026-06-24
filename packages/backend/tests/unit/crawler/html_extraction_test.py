"""Tests for trafilatura-based HTML extraction."""

from src.crawler import ClauseaCrawler
from src.crawler.html_extraction import extract_with_trafilatura


def test_extract_with_trafilatura_mediawiki_terms():
    html = """
    <html class="client-nojs vector-feature-limited-width-content-enabled">
      <body>
        <main id="content">
          <div id="mw-content-text" class="mw-parser-output">
            <h1>Terms of Use</h1>
            <p>These terms govern your use of Wikimedia projects and services.</p>
            <p>Users must comply with applicable law and respect community guidelines.</p>
            <p>Content may be reused under free licenses when attribution requirements are met.</p>
          </div>
        </main>
      </body>
    </html>
    """
    result = extract_with_trafilatura(
        html, url="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"
    )
    assert result is not None
    text, _markdown = result
    assert "Terms of Use" in text
    assert "Wikimedia projects" in text


def test_parse_html_string_prefers_trafilatura_over_selectors():
    body_para = (
        "This Terms of Service section explains the legal agreement between you and "
        "the company. It describes your rights, obligations, liability, dispute "
        "resolution, governing law, and the conditions under which the service is "
        "provided. "
    )
    sections = "".join(
        f'<div data-testid="CEPHtmlSection"><h2>Section {i}</h2><p>{body_para}</p></div>'
        for i in range(8)
    )
    html = f"""
    <!doctype html>
    <html>
      <body>
        <div data-testid="related-articles-card">
          <h3>Related articles</h3>
          <a href="/help/article/1">About the updates to our Terms</a>
        </div>
        <div data-testid="article-body-container">
          {sections}
        </div>
      </body>
    </html>
    """
    crawler = ClauseaCrawler()
    title, text, _markdown, _metadata, _links = crawler._parse_html_string(
        html, "https://example.com/terms"
    )

    assert title == ""
    assert text.count("This Terms of Service section explains") == 8
    assert "Section 7" in text
    assert len(text) > 1000


def test_parse_html_string_strips_cookie_banner_with_trafilatura():
    html = """
    <!doctype html>
    <html>
      <body>
        <div id="cookie-banner">Accept cookies</div>
        <section class="cookie-policy legal-content">
          <h1>Cookie Policy</h1>
          <p>
            This Cookie Policy explains how we use cookies, similar technologies,
            and related tracking tools. We process personal data for analytics,
            security, and service improvement. You can manage your consent
            preferences, and you have rights under applicable privacy laws.
          </p>
          <p>
            We may update this policy from time to time. Please review this
            policy periodically for changes affecting data protection and usage.
          </p>
        </section>
      </body>
    </html>
    """
    crawler = ClauseaCrawler()
    _title, text, _markdown, _metadata, _links = crawler._parse_html_string(
        html, "https://example.com/cookies"
    )

    assert "Cookie Policy" in text
    assert "data protection" in text.lower()
    assert "Accept cookies" not in text
