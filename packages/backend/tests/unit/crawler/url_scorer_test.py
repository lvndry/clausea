from src.crawler import URLScorer


def test_url_scorer_boosts_common_legal_phrases_in_anchor_text() -> None:
    scorer = URLScorer()

    score = scorer.score_url(
        "https://www.airbnb.com/help/article/2860",
        anchor_text="Privacy Policy Supplement",
    )

    assert score >= 25.0


def test_url_scorer_boosts_terms_of_service_phrase_in_anchor_text() -> None:
    scorer = URLScorer()

    score = scorer.score_url(
        "https://example.com/support/article/123",
        anchor_text="Terms of Service",
    )

    assert score >= 25.0


def test_url_scorer_opaque_url_with_legal_anchor_scores_well() -> None:
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


def test_url_scorer_opaque_url_without_anchor_scores_low() -> None:
    """Opaque URLs with no anchor text should score near zero."""
    scorer = URLScorer()

    score = scorer.score_url("https://www.airbnb.com/help/article/2908")

    assert score < 2.0


def test_url_scorer_cookie_policy_anchor() -> None:
    scorer = URLScorer()

    score = scorer.score_url(
        "https://www.airbnb.fr/help/article/2866",
        anchor_text="Cookie Policy",
    )

    assert score >= 20.0
