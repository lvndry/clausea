"""The convergence budget stops a crawl that keeps reading non-policy pages.

Production crawls breadth-first with min_legal_score=0, so every same-domain link is
followed — on large consumer sites that means wandering hundreds of marketing pages and
never converging within the pipeline's time budget. Once policy content is found, the
crawl stops after `no_policy_page_budget` consecutive pages with none more; it never
stops before any policy page is seen.
"""

from src.crawler import ClauseaCrawler


def _crawler(budget: int) -> ClauseaCrawler:
    return ClauseaCrawler(no_policy_page_budget=budget, respect_robots_txt=False)


def test_no_stop_before_any_policy_found() -> None:
    crawler = _crawler(5)
    # Even far past the budget, never converge until at least one policy page is seen.
    assert crawler._has_converged(found_policy=False, pages_since_policy_hit=999) is False


def test_no_stop_while_within_budget() -> None:
    crawler = _crawler(50)
    assert crawler._has_converged(found_policy=True, pages_since_policy_hit=49) is False


def test_stops_once_budget_exceeded_after_a_hit() -> None:
    crawler = _crawler(50)
    assert crawler._has_converged(found_policy=True, pages_since_policy_hit=50) is True


def test_budget_zero_disables_convergence() -> None:
    crawler = _crawler(0)
    assert crawler._has_converged(found_policy=True, pages_since_policy_hit=10_000) is False
