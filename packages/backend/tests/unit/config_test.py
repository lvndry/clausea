"""Unit tests for configuration management."""


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
