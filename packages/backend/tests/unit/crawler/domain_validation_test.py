from src.crawler import ClauseaCrawler


def test_is_allowed_domain_subdomains():
    # Test that subdomains are allowed by default
    crawler = ClauseaCrawler(allowed_domains=["airbnb.com"])

    # Exact match
    assert crawler.is_allowed_domain("https://airbnb.com/help") is True

    # Subdomain match
    assert crawler.is_allowed_domain("https://www.airbnb.com/help") is True
    assert crawler.is_allowed_domain("https://help.airbnb.com/article/1") is True
    assert crawler.is_allowed_domain("https://uk.airbnb.com/rooms") is True

    # Suffix/ccTLD match (e.g., airbnb.com.ua should be allowed if airbnb.com is allowed)
    # The user specifically mentioned airbnb.com.ua being rejected when airbnb.com is allowed.
    assert crawler.is_allowed_domain("https://www.airbnb.com.ua/help/article/2908") is True
    assert crawler.is_allowed_domain("https://airbnb.com.ua") is True

    # Reverse match (e.g., airbnb.com should be allowed if airbnb.com.ua is allowed)
    crawler_ua = ClauseaCrawler(allowed_domains=["airbnb.com.ua"])
    assert crawler_ua.is_allowed_domain("https://airbnb.com") is True
    assert crawler_ua.is_allowed_domain("https://www.airbnb.com") is True


def test_should_crawl_url_subdomains():
    crawler = ClauseaCrawler(allowed_domains=["airbnb.com"])

    # Should allow these
    assert crawler.should_crawl_url("https://www.airbnb.com/help", "https://airbnb.com", 1) is True
    assert (
        crawler.should_crawl_url(
            "https://www.airbnb.com.ua/help/article/2908", "https://airbnb.com", 1
        )
        is True
    )

    # Should still reject completely different domains
    assert crawler.should_crawl_url("https://google.com", "https://airbnb.com", 1) is False
    assert crawler.should_crawl_url("https://notairbnb.com", "https://airbnb.com", 1) is False


def test_is_allowed_domain_multiple_allowed():
    crawler = ClauseaCrawler(allowed_domains=["example.com", "test.org"])

    assert crawler.is_allowed_domain("https://sub.example.com") is True
    assert crawler.is_allowed_domain("https://dev.test.org") is True
    # .org.au is a recognized public suffix, so domain='test' matches
    assert crawler.is_allowed_domain("https://test.org.au") is True

    assert crawler.is_allowed_domain("https://other.com") is False
    # .com.uk is NOT a recognized public suffix (unlike .co.uk),
    # so tldextract parses domain='com' which doesn't match 'example'
    assert crawler.is_allowed_domain("https://example.com.uk") is False


def test_is_allowed_domain_rejects_false_positives():
    """Ensure unrelated domains are rejected even if they share a TLD suffix."""
    crawler = ClauseaCrawler(allowed_domains=["airbnb.com"])

    # Completely different domains must be rejected
    assert crawler.is_allowed_domain("https://evil.com") is False
    assert crawler.is_allowed_domain("https://notairbnb.com") is False
    assert crawler.is_allowed_domain("https://airbnb-fake.com") is False
    assert crawler.is_allowed_domain("https://myairbnbclone.com") is False
    assert crawler.is_allowed_domain("https://example.org") is False
