import pytest

from src.crawler import _MIRROR_SUBDOMAIN_RE, ClauseaCrawler, URLScorer


class TestURLScorerGlossaryGuard:
    """'terms' used as glossary/terminology must not score like Terms of Service."""

    def test_chess_terms_glossary_scores_zero(self) -> None:
        scorer = URLScorer()
        assert scorer.score_url("https://www.duolingo.com/chess/terms/absolute-pin") == 0.0
        assert (
            scorer.score_url("https://www.duolingo.com/chess/terms/what-is-checkmate-in-chess")
            == 0.0
        )

    def test_real_terms_pages_keep_high_score(self) -> None:
        scorer = URLScorer()
        # Terminal /terms and legal-qualified sub-paths must remain strong signals.
        assert scorer.score_url("https://example.com/terms") >= 5.0
        assert scorer.score_url("https://example.com/legal/terms/service") >= 5.0
        assert scorer.score_url("https://example.com/help/terms") >= 5.0
        assert scorer.score_url("https://example.com/policies/terms/cookies") >= 5.0

    def test_glossary_guard_does_not_touch_privacy_or_cookies(self) -> None:
        scorer = URLScorer()
        assert scorer.score_url("https://www.duolingo.com/privacy") >= 5.0
        assert scorer.score_url("https://www.duolingo.com/cookies") >= 5.0


class TestURLScorerNonPolicyGalleries:
    """User-generated gallery sections must not score as policy documents.

    Pages like /templates/legal-case-tracking/exp123 contain legal keywords in
    their slugs and otherwise pass the relevance gate, triggering wasteful
    browser renders — but they are never the company's own policy documents.
    """

    def test_template_and_universe_pages_score_zero(self) -> None:
        scorer = URLScorer()
        assert (
            scorer.score_url(
                "https://www.airtable.com/templates/legal-case-tracking-and-billing/exp2AvdLUMYh4kXoT"
            )
            == 0.0
        )
        assert (
            scorer.score_url(
                "https://www.airtable.com/universe/exps1dC0QDfDT8E7D/the-startup-legal-setup-guide"
            )
            == 0.0
        )
        assert scorer.score_url("https://example.com/marketplace/blk5/privacy-toolkit") == 0.0

    def test_anchor_text_does_not_rescue_gallery_pages(self) -> None:
        scorer = URLScorer()
        # Even a strong legal anchor must not escalate a template gallery page.
        assert (
            scorer.score_url(
                "https://www.airtable.com/templates/privacy-policy/exp9",
                anchor_text="Privacy Policy",
            )
            == 0.0
        )

    def test_real_policy_paths_are_unaffected(self) -> None:
        scorer = URLScorer()
        # These were correctly rendered in production and must keep scoring high.
        assert scorer.score_url("https://www.airtable.com/company/subprocessors") >= 4.0
        assert scorer.score_url("https://support.airtable.com/docs/gdpr-at-airtable") >= 4.0
        assert scorer.score_url("https://example.com/legal/privacy") >= 5.0


class TestURLScorerAnchorTextBoost:
    """Anchor text should be the dominant signal for opaque URLs."""

    def test_boosts_common_legal_phrases_in_anchor_text(self) -> None:
        scorer = URLScorer()

        score = scorer.score_url(
            "https://www.airbnb.com/help/article/2860",
            anchor_text="Privacy Policy Supplement",
        )

        assert score >= 25.0

    def test_boosts_terms_of_service_phrase_in_anchor_text(self) -> None:
        scorer = URLScorer()

        score = scorer.score_url(
            "https://example.com/support/article/123",
            anchor_text="Terms of Service",
        )

        assert score >= 25.0

    def test_opaque_url_with_legal_anchor_scores_well(self) -> None:
        """URLs like /help/article/2908 should score high when anchor says 'Terms of Service'."""
        scorer = URLScorer()

        score = scorer.score_url(
            "https://www.airbnb.com/help/article/2908",
            anchor_text="Terms of Service",
        )

        # Should be competitive with a URL that has legal keywords in the path
        path_score = scorer.score_url("https://example.com/terms-of-service")
        assert score >= path_score * 0.8, (
            f"Opaque URL with legal anchor ({score:.1f}) should be comparable to "
            f"legal-path URL ({path_score:.1f})"
        )

    def test_opaque_url_without_anchor_scores_low(self) -> None:
        """Opaque URLs with no anchor text should score near zero."""
        scorer = URLScorer()

        score = scorer.score_url("https://www.airbnb.com/help/article/2908")

        assert score < 2.0

    def test_cookie_policy_anchor(self) -> None:
        scorer = URLScorer()

        score = scorer.score_url(
            "https://www.airbnb.fr/help/article/2866",
            anchor_text="Cookie Policy",
        )

        assert score >= 20.0


class TestURLScorerNeutralPaths:
    """Paths like /help, /about, /support should NOT be penalised.

    Many companies host policy documents under these sections (e.g. Airbnb
    Terms of Service at /help/article/2908).  Previous negative weights for
    these keywords caused the pipeline to deprioritise legitimate legal URLs.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.airbnb.com/help/article/2908",
            "https://example.com/about/legal",
            "https://example.com/support/privacy",
            "https://example.com/blog/policy-update",
        ],
    )
    def test_common_paths_are_not_penalised(self, url: str) -> None:
        """URLs under /help, /about, /support, /blog should score >= 0."""
        scorer = URLScorer()
        score = scorer.score_url(url)
        assert score >= 0.0, f"URL {url} should not receive a negative score, got {score}"

    def test_contact_path_is_penalised(self) -> None:
        """Contact pages are not policy documents."""
        scorer = URLScorer()
        score_contact = scorer.score_url("https://example.com/contact")
        score_legal = scorer.score_url("https://example.com/legal/privacy")
        assert score_contact < score_legal

    def test_news_path_is_still_penalised(self) -> None:
        scorer = URLScorer()
        score_news = scorer.score_url("https://example.com/news/announcement")
        score_legal = scorer.score_url("https://example.com/legal/terms")
        assert score_news < score_legal


class TestParentPageBoost:
    """Links discovered on pages with legal indicators in title/metadata
    should receive a score boost in best_first strategy."""

    def _make_crawler(
        self, strategy: str = "best_first", min_legal_score: float = 0.0
    ) -> ClauseaCrawler:
        crawler = ClauseaCrawler(
            respect_robots_txt=False,
            strategy=strategy,
            min_legal_score=min_legal_score,
            allowed_domains=["example.com"],
        )
        # Prevent speculative URL generation so tests only see the links we pass in
        crawler._sitemap_seeded = True
        return crawler

    def test_legal_hub_page_boosts_discovered_links(self) -> None:
        crawler = self._make_crawler()

        legal_metadata = {"title": "Airbnb Legal Resources"}
        boost = crawler._compute_parent_page_boost(legal_metadata)
        assert boost > 0, "Pages with legal keywords in title should produce a boost"

    def test_non_legal_page_gives_no_boost(self) -> None:
        crawler = self._make_crawler()

        generic_metadata = {"title": "Airbnb Experiences"}
        boost = crawler._compute_parent_page_boost(generic_metadata)
        assert boost == 0.0

    def test_boost_applies_only_to_best_first(self) -> None:
        """BFS/DFS strategies should not be affected by parent page signals."""
        crawler = self._make_crawler(strategy="bfs")

        crawler.add_urls_to_queue(
            [{"url": "https://example.com/article/123", "text": ""}],
            "https://example.com",
            depth=1,
            page_metadata={"title": "Legal Resources"},
        )

        # BFS queues have no scoring — just verify the URL was added
        assert len(crawler.url_queue) == 1

    def test_best_first_applies_parent_boost(self) -> None:
        """In best_first, links from a legal hub page should score higher."""
        scorer = URLScorer()

        # Opaque URL without any context
        base_score = scorer.score_url("https://example.com/article/123", anchor_text="Some article")

        crawler = self._make_crawler()

        crawler.add_urls_to_queue(
            [{"url": "https://example.com/article/123", "text": "Some article"}],
            "https://example.com",
            depth=1,
            page_metadata={"title": "Privacy and Terms"},
        )

        assert len(crawler.url_priority_queue) == 1
        neg_score, url, _depth, _base = crawler.url_priority_queue[0]
        actual_score = -neg_score

        # Score should exceed the base URL score thanks to the parent boost
        assert actual_score > base_score, (
            f"Parent-boosted score ({actual_score:.1f}) should exceed base score ({base_score:.1f})"
        )

    def test_parent_boost_does_not_revive_gallery_pages(self) -> None:
        """A legal-hub parent boost must never lift a hard-excluded section
        (templates/universe/gallery) past min_legal_score.

        Regression: CapCut's ``/trust/legal`` hub links to ``/template/*`` pages.
        The scorer zeroes those sections, but the parent boost was added on top,
        reviving them past the gate and wasting a browser render on each.
        """
        crawler = self._make_crawler(min_legal_score=2.5)

        crawler.add_urls_to_queue(
            [
                {"url": "https://example.com/template/holiday", "text": "Holiday templates"},
                {"url": "https://example.com/templates/legal-case/exp9", "text": "Legal case"},
                # A genuinely opaque policy link on the same hub must still be boosted in.
                {"url": "https://example.com/article/2908", "text": "Terms of Service"},
            ],
            "https://example.com",
            depth=1,
            page_metadata={"title": "Legal Resources"},
        )

        queued = {url for _neg, url, _depth, _base in crawler.url_priority_queue}
        assert "https://example.com/template/holiday" not in queued
        assert "https://example.com/templates/legal-case/exp9" not in queued
        # The boost still works for non-excluded opaque policy URLs.
        assert "https://example.com/article/2908" in queued


class TestMinLegalScoreFilter:
    """best_first strategy should skip URLs below min_legal_score."""

    def _make_crawler(self, min_legal_score: float = 5.0) -> ClauseaCrawler:
        crawler = ClauseaCrawler(
            respect_robots_txt=False,
            strategy="best_first",
            min_legal_score=min_legal_score,
            allowed_domains=["example.com"],
        )
        # Prevent speculative URL generation so tests only see the links we pass in
        crawler._sitemap_seeded = True
        return crawler

    def test_low_scoring_url_filtered_by_min_legal_score(self) -> None:
        crawler = self._make_crawler(min_legal_score=5.0)

        # This URL + anchor combo will score well below 5.0
        crawler.add_urls_to_queue(
            [{"url": "https://example.com/blog/random-post", "text": "Read more"}],
            "https://example.com",
            depth=1,
        )

        assert len(crawler.url_priority_queue) == 0, (
            "URL scoring below min_legal_score should not be added to best_first queue"
        )

    def test_high_scoring_url_passes_min_legal_score(self) -> None:
        crawler = self._make_crawler(min_legal_score=5.0)

        crawler.add_urls_to_queue(
            [{"url": "https://example.com/article/99", "text": "Terms of Service"}],
            "https://example.com",
            depth=1,
        )

        assert len(crawler.url_priority_queue) == 1, (
            "URL with legal anchor text should pass min_legal_score filter"
        )


class TestURLScorerAuthAndRedirectParams:
    """Login walls fronting policy URLs must not inherit the policy's relevance."""

    def test_login_with_policy_return_to_scores_zero(self) -> None:
        scorer = URLScorer()
        # Real case from the github crawl: a login wall whose return_to embeds the policy
        # URL must not score as if it were the policy (it would burn a browser render).
        url = (
            "https://github.com/login?return_to=https://github.com/github/docs/blob/"
            "main/content/site-policy/github-terms/github-terms-of-service.md"
        )
        assert scorer.score_url(url) == 0.0

    def test_bare_auth_paths_score_zero(self) -> None:
        scorer = URLScorer()
        for url in (
            "https://example.com/login",
            "https://example.com/sign-in",
            "https://example.com/account/signup",
            "https://example.com/logout",
            "https://example.com/oauth/authorize",
            "https://example.com/sso",
        ):
            assert scorer.score_url(url) == 0.0, url

    def test_redirect_param_does_not_inflate_non_auth_page(self) -> None:
        scorer = URLScorer()
        # A non-auth page carrying a policy URL in a redirect param should be scored on
        # its own path, not on the redirect target.
        with_param = scorer.score_url("https://example.com/home?next=/privacy-policy")
        bare = scorer.score_url("https://example.com/home")
        assert with_param == bare

    def test_real_policy_pages_still_score_high(self) -> None:
        scorer = URLScorer()
        # Regression guard: the fix must not depress genuine policy URLs.
        assert scorer.score_url("https://example.com/privacy-policy") >= 5.0
        assert (
            scorer.score_url(
                "https://docs.github.com/en/site-policy/github-terms/github-terms-of-service"
            )
            >= 5.0
        )


class TestMirrorSubdomainExclusion:
    """Non-production mirror subdomains duplicate prod pages and must not be crawled."""

    def _crawler(self):
        return ClauseaCrawler(allowed_domains=["github.com"], follow_external_links=False)

    def test_internal_mirror_rejected(self) -> None:
        c = self._crawler()
        assert not c.should_crawl_url(
            "https://docs-internal.github.com/en/site-policy/github-terms/github-terms-of-service",
            "https://docs.github.com/en/site-policy",
            1,
        )
        assert not c.should_crawl_url("https://staging.github.com/legal", "https://github.com", 1)
        assert not c.should_crawl_url("https://preview.github.com/legal", "https://github.com", 1)

    def test_real_subdomains_still_allowed(self) -> None:
        c = self._crawler()
        # docs.github.com (the canonical surface) and a "developer" subdomain must NOT be
        # caught by the mirror filter.
        assert c.should_crawl_url(
            "https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
            "https://docs.github.com/en/site-policy",
            1,
        )

    def test_regex_catches_real_mirrors(self) -> None:
        for subdomain in ("docs-internal", "staging", "preview", "preview.staging"):
            assert _MIRROR_SUBDOMAIN_RE.search(subdomain), subdomain

    def test_regex_spares_legit_subdomains_with_token_prefix(self) -> None:
        # Hyphenated subdomains that merely start with a trigger token are legitimate, not
        # mirrors — rejecting them silently drops real pages.
        for subdomain in (
            "preview-blog",
            "staging-guide",
            "my-internal-tool",
            "internal-docs",
            "international",
            "www",
        ):
            assert not _MIRROR_SUBDOMAIN_RE.search(subdomain), subdomain
