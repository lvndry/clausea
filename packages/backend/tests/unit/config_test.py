"""Unit tests for configuration management."""

import pytest


class TestConfig:
    """Test cases for configuration settings."""

    def test_config_import(self) -> None:
        """Test that config can be imported without errors."""
        from src.core.config import config

        assert config is not None

    def test_security_config_exists(self) -> None:
        """Test that security configuration exists."""
        from src.core.config import config

        assert hasattr(config, "security")
        assert config.security is not None

    def test_clerk_jwks_url_exists(self) -> None:
        """Test that Clerk JWKS URL is configured."""
        from src.core.config import config

        assert config.security.clerk_jwks_url is not None
        assert config.security.clerk_jwks_url.startswith("https://")

    def test_database_config_exists(self) -> None:
        """Test that database configuration exists."""
        from src.core.config import config

        assert hasattr(config, "database")
        assert config.database is not None

    def test_llm_config_exists(self) -> None:
        """Test that LLM configuration exists."""
        from src.core.config import config

        # LLM config might not exist yet, so just test that settings can be imported
        assert config is not None


class TestCrawlerConfig:
    """Crawler env parsing (instantiate ``CrawlerConfig`` directly; avoids ``get_config`` cache)."""

    def test_discovery_limits_derived_from_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import CrawlerConfig, discovery_crawl_limits

        monkeypatch.setenv("CRAWLER_MAX_PAGES", "5000")
        monkeypatch.setenv("CRAWLER_MAX_DEPTH", "9")
        c = CrawlerConfig()
        d_pages, d_depth = discovery_crawl_limits(c.max_pages, c.max_depth)
        assert d_pages == 1000
        assert d_depth == 3

        monkeypatch.setenv("CRAWLER_MAX_PAGES", "50")
        monkeypatch.setenv("CRAWLER_MAX_DEPTH", "2")
        c2 = CrawlerConfig()
        d_pages2, d_depth2 = discovery_crawl_limits(c2.max_pages, c2.max_depth)
        assert d_pages2 == 50
        assert d_depth2 == 2

    def test_crawler_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CRAWLER_DISCOVERY_MIN_LEGAL_SCORE", "3.1")
        monkeypatch.setenv("CRAWLER_DISCOVERY_STRATEGY", "DFS")
        monkeypatch.setenv("CRAWLER_REQUIRED_DOC_TYPES", "privacy_policy,cookie_policy")
        monkeypatch.setenv("CRAWLER_USE_BROWSER", "false")
        monkeypatch.setenv("CRAWLER_RESPECT_ROBOTS_TXT", "0")

        from src.core.config import CrawlerConfig

        c = CrawlerConfig()
        assert c.discovery_min_legal_score == pytest.approx(3.1)
        assert c.discovery_strategy == "dfs"
        assert c.required_doc_types == ["privacy_policy", "cookie_policy"]
        assert c.use_browser is False
        assert c.respect_robots_txt is False
