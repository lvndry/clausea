import pytest

from src.crawler import ClauseaCrawler, URLScorer


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
        neg_score, url, _depth = crawler.url_priority_queue[0]
        actual_score = -neg_score

        # Score should exceed the base URL score thanks to the parent boost
        assert actual_score > base_score, (
            f"Parent-boosted score ({actual_score:.1f}) should exceed base score ({base_score:.1f})"
        )


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
