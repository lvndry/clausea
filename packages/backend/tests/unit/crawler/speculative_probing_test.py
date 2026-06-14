"""Speculative policy-URL probing runs only as a last resort.

Probing the full guessed-path list is the accepted cost of recall (recall over
speed), but it's skipped when the seed page already surfaces policy links —
link-following will reach those pages, so blind probing would be redundant.
"""

from src.crawler import ClauseaCrawler


class TestSpeculativeProbingGate:
    def test_skipped_when_seed_page_links_to_policy(self):
        crawler = ClauseaCrawler()
        crawler._sitemap_seeded = False
        links = [
            {"url": "https://example.com/about", "text": "About"},
            {"url": "https://example.com/privacy-policy", "text": "Privacy Policy"},
        ]
        crawler.add_urls_to_queue(links, "https://example.com", depth=0)
        # The seed page already leads to a policy page — no blind probing.
        assert crawler._speculative_urls == set()

    def test_runs_when_seed_page_has_no_policy_leads(self):
        crawler = ClauseaCrawler()
        crawler._sitemap_seeded = False
        links = [
            {"url": "https://example.com/pricing", "text": "Pricing"},
            {"url": "https://example.com/features", "text": "Features"},
        ]
        crawler.add_urls_to_queue(links, "https://example.com", depth=0)
        assert len(crawler._speculative_urls) > 0

    def test_skipped_when_sitemap_already_seeded(self):
        crawler = ClauseaCrawler()
        crawler._sitemap_seeded = True
        links = [{"url": "https://example.com/pricing", "text": "Pricing"}]
        crawler.add_urls_to_queue(links, "https://example.com", depth=0)
        assert crawler._speculative_urls == set()
