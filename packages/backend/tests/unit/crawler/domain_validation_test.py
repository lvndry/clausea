from src.crawler import ClauseaCrawler


def test_is_allowed_domain_subdomains():
    crawler = ClauseaCrawler(allowed_domains=["airbnb.com"])

    # Exact match
    assert crawler.is_allowed_domain("https://airbnb.com/help") is True

    # Direct subdomain match
    assert crawler.is_allowed_domain("https://www.airbnb.com/help") is True
    assert crawler.is_allowed_domain("https://help.airbnb.com/article/1") is True
    assert crawler.is_allowed_domain("https://uk.airbnb.com/rooms") is True

    # A different registered domain (e.g. airbnb.com.ua) is NOT a subdomain of
    # airbnb.com, so it must be declared explicitly rather than drifting in.
    assert crawler.is_allowed_domain("https://www.airbnb.com.ua/help/article/2908") is False
    assert crawler.is_allowed_domain("https://airbnb.com.ua") is False

    # And the reverse: declaring airbnb.com.ua does not pull in airbnb.com.
    crawler_ua = ClauseaCrawler(allowed_domains=["airbnb.com.ua"])
    assert crawler_ua.is_allowed_domain("https://airbnb.com") is False
    assert crawler_ua.is_allowed_domain("https://www.airbnb.com") is False

    # Declaring both registered domains allows both.
    crawler_both = ClauseaCrawler(allowed_domains=["airbnb.com", "airbnb.com.ua"])
    assert crawler_both.is_allowed_domain("https://www.airbnb.com") is True
    assert crawler_both.is_allowed_domain("https://www.airbnb.com.ua") is True


def test_should_crawl_url_subdomains():
    crawler = ClauseaCrawler(allowed_domains=["airbnb.com"])

    # Should allow these
    assert crawler.should_crawl_url("https://www.airbnb.com/help", "https://airbnb.com", 1) is True

    # A different registered domain is out of scope unless explicitly declared.
    assert (
        crawler.should_crawl_url(
            "https://www.airbnb.com.ua/help/article/2908", "https://airbnb.com", 1
        )
        is False
    )

    # Should still reject completely different domains
    assert crawler.should_crawl_url("https://google.com", "https://airbnb.com", 1) is False
    assert crawler.should_crawl_url("https://notairbnb.com", "https://airbnb.com", 1) is False


def test_is_allowed_domain_multiple_allowed():
    crawler = ClauseaCrawler(allowed_domains=["example.com", "test.org"])

    assert crawler.is_allowed_domain("https://sub.example.com") is True
    assert crawler.is_allowed_domain("https://dev.test.org") is True
    # test.org.au is a distinct registered domain from test.org, so it is not allowed.
    assert crawler.is_allowed_domain("https://test.org.au") is False

    assert crawler.is_allowed_domain("https://other.com") is False
    # .com.uk is NOT a recognized public suffix (unlike .co.uk),
    # and example.com.uk is not a subdomain of example.com either way.
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


def test_is_allowed_domain_denies_declared_subdomain():
    # aws.amazon.com IS a subdomain of amazon.com, so the subdomain rule alone would
    # let it drift in. The crawl_denied_domains list is what blocks it for amazon.
    crawler = ClauseaCrawler(allowed_domains=["amazon.com"], denied_domains=["aws.amazon.com"])
    assert crawler.is_allowed_domain("https://aws.amazon.com/privacy") is False
    assert crawler.is_allowed_domain("https://foo.aws.amazon.com/x") is False
    assert crawler.is_allowed_domain("https://www.amazon.com/privacy") is True
    assert crawler.is_allowed_domain("https://amazon.com/privacy") is True

    # Without the deny list, aws.amazon.com is allowed by the subdomain rule —
    # this is exactly why amazon must declare it in crawl_denied_domains.
    crawler_no_deny = ClauseaCrawler(allowed_domains=["amazon.com"])
    assert crawler_no_deny.is_allowed_domain("https://aws.amazon.com/privacy") is True

    # Declaring aws.amazon.com directly allows it (exact hostname match).
    crawler_aws = ClauseaCrawler(allowed_domains=["aws.amazon.com"])
    assert crawler_aws.is_allowed_domain("https://aws.amazon.com/privacy") is True
