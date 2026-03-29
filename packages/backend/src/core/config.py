import os
from enum import Enum
from functools import lru_cache

import structlog
from dotenv import load_dotenv

load_dotenv()

logger = structlog.get_logger(service="config")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


_DISCOVERY_PAGE_CAP = 1000
_DISCOVERY_DEPTH_CAP = 3


def discovery_crawl_limits(max_pages: int, max_depth: int) -> tuple[int, int]:
    """Return (discovery_max_pages, discovery_max_depth) from the global crawl budget."""
    return (
        min(max_pages, _DISCOVERY_PAGE_CAP),
        min(max_depth, _DISCOVERY_DEPTH_CAP),
    )


class StorageType(Enum):
    """Storage type enumeration"""

    LOCAL = "local"
    REMOTE = "remote"


class AppConfig:
    """Application configuration"""

    def __init__(self) -> None:
        self.name: str = "Clausea"
        self.version: str = "0.1.0"
        self.env: str = os.getenv("ENVIRONMENT", "development")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.debug: bool = False

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.debug or self.env.lower() == "development"


class DatabaseConfig:
    """Database configuration"""

    def __init__(self) -> None:
        self.mongodb_uri: str = os.getenv("MONGO_URI") or ""
        self.mongodb_ssl_ca_certs: str | None = os.getenv("MONGODB_SSL_CA_CERTS")
        self.mongodb_ssl_certfile: str | None = os.getenv("MONGODB_SSL_CERTFILE")
        self.mongodb_ssl_keyfile: str | None = os.getenv("MONGODB_SSL_KEYFILE")
        # TODO: Change to clausea
        self.mongodb_database: str = os.getenv("MONGODB_DATABASE", "clausea")

    @property
    def database_url(self) -> str | None:
        """Get the database URL with fallback"""
        return self.mongodb_uri or None


class SecurityConfig:
    """Security configuration"""

    def __init__(self) -> None:
        self.clerk_jwks_url: str = os.getenv(
            "CLERK_JWKS_URL",
            "https://calm-squid-68.clerk.accounts.dev/.well-known/jwks.json",
        )
        # API key for service-to-service authentication (e.g., Streamlit dashboard)
        self.service_api_key: str | None = os.getenv("SERVICE_API_KEY")


class CorsConfig:
    """CORS configuration"""

    def __init__(self) -> None:
        cors_origins_env = os.getenv("CORS_ORIGINS", "*")

        # In production, we should not allow "*" for security
        env: str = os.getenv("ENVIRONMENT", "development")
        if env.lower() == "production" and cors_origins_env == "*":
            logger.warning("CORS_ORIGINS is set to '*' in production - this is a security risk!")
            self.origins = ["*"]
        else:
            self.origins = cors_origins_env.split(",") if cors_origins_env != "*" else ["*"]

        self.methods: list[str] = ["*"]
        self.headers: list[str] = ["*"]
        self.credentials: bool = True

    def __str__(self) -> str:
        """String representation of CORS configuration"""
        return f"CorsConfig(origins={self.origins}, methods={self.methods}, headers={self.headers}, credentials={self.credentials})"

    @property
    def is_secure(self) -> bool:
        """Check if CORS configuration is secure for production"""
        if config.app.env.lower() == "production":
            return "*" not in self.origins and len(self.origins) > 0
        return True


class ApiConfig:
    """API configuration"""

    def __init__(self) -> None:
        self.rate_limit_default: str = os.getenv("API_RATE_LIMIT", "120/minute")


class EmbeddingConfig:
    """Embedding configuration"""

    def __init__(self) -> None:
        # Batch size for processing chunks
        self.batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", 50))
        # Pinecone upsert batch size
        self.upsert_batch_size: int = int(os.getenv("EMBEDDING_UPSERT_BATCH_SIZE", 100))
        # Chunk size for text splitting (characters not tokens)
        self.chunk_size: int = int(os.getenv("EMBEDDING_CHUNK_SIZE", 4000))
        # Chunk overlap for text splitting (characters not tokens)
        self.chunk_overlap: int = int(os.getenv("EMBEDDING_CHUNK_OVERLAP", 500))


class TrackingConfig:
    """Tracking configuration"""

    def __init__(self) -> None:
        self.posthog_api_key: str | None = os.getenv("POSTHOG_API_KEY")
        self.posthog_host: str = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
        self.tracking_enabled: bool = self._is_tracking_enabled()

    def _is_tracking_enabled(self) -> bool:
        """Check if tracking is enabled based on environment variables"""
        # Check if tracking is explicitly disabled
        tracking_enabled_env = os.getenv("TRACKING_ENABLED", "true").lower()
        if tracking_enabled_env in ("false", "0", "no"):
            return False

        # Check if PostHog API key is available
        return self.posthog_api_key is not None


class PaddleConfig:
    """Paddle payment configuration"""

    def __init__(self) -> None:
        self.api_key: str | None = os.getenv("PADDLE_API_KEY")
        self.webhook_secret: str | None = os.getenv("PADDLE_WEBHOOK_SECRET")
        self.environment: str = os.getenv("PADDLE_ENVIRONMENT", "sandbox")
        self.checkout_url: str | None = os.getenv("PADDLE_CHECKOUT_URL")
        # Pro tier pricing
        self.price_pro_monthly: str | None = os.getenv("PADDLE_PRICE_PRO_MONTHLY")
        self.price_pro_annual: str | None = os.getenv("PADDLE_PRICE_PRO_ANNUAL")


class CrawlerConfig:
    """Crawler and policy-pipeline crawl settings (env-tunable)."""

    def __init__(self) -> None:
        self.max_pages: int = int(os.getenv("CRAWLER_MAX_PAGES", "2000"))
        self.max_depth: int = int(os.getenv("CRAWLER_MAX_DEPTH", "5"))

        # --- Concurrency & politeness ---
        self.concurrent_limit: int = int(os.getenv("CRAWLER_CONCURRENT_LIMIT", "20"))
        self.delay_between_requests: float = float(
            os.getenv("CRAWLER_DELAY_BETWEEN_REQUESTS", "1.0")
        )
        self.rate_limit_jitter: float = float(os.getenv("CRAWLER_RATE_LIMIT_JITTER", "0.2"))
        self.timeout: int = int(os.getenv("CRAWLER_TIMEOUT", "30"))

        # --- Pipeline behavior ---
        self.respect_robots_txt: bool = _env_bool("CRAWLER_RESPECT_ROBOTS_TXT", True)
        self.max_parallel_products: int = int(os.getenv("CRAWLER_MAX_PARALLEL_PRODUCTS", "3"))
        self.use_browser: bool = _env_bool("CRAWLER_USE_BROWSER", True)
        _proxy = os.getenv("CRAWLER_PROXY")
        self.proxy: str | None = _proxy.strip() if _proxy and _proxy.strip() else None

        self.discovery_min_legal_score: float = float(
            os.getenv("CRAWLER_DISCOVERY_MIN_LEGAL_SCORE", "2.5")
        )
        self.discovery_strategy: str = (
            os.getenv("CRAWLER_DISCOVERY_STRATEGY", "best_first").strip().lower()
        )
        self.fallback_strategy: str = os.getenv("CRAWLER_FALLBACK_STRATEGY", "bfs").strip().lower()
        self.fallback_min_legal_score: float = float(
            os.getenv("CRAWLER_FALLBACK_MIN_LEGAL_SCORE", "1.5")
        )
        self.crawler_strategy: str = os.getenv("CRAWLER_STRATEGY", "bfs").strip().lower()

        self.min_docs_before_fallback: int = int(os.getenv("CRAWLER_MIN_DOCS_BEFORE_FALLBACK", "2"))
        _req = os.getenv("CRAWLER_REQUIRED_DOC_TYPES", "privacy_policy,terms_of_service")
        self.required_doc_types: list[str] = [x.strip() for x in _req.split(",") if x.strip()]

        self.user_agent: str = os.getenv(
            "CRAWLER_USER_AGENT",
            "ClauseaCrawler/2.0 (Policy Document Discovery Bot of Clausea)",
        )


class Config:
    """Application configuration with nested configuration objects"""

    def __init__(self) -> None:
        self.app = AppConfig()
        self.database = DatabaseConfig()
        self.security = SecurityConfig()
        self.cors = CorsConfig()
        self.api = ApiConfig()
        self.embedding = EmbeddingConfig()
        self.tracking = TrackingConfig()
        self.paddle = PaddleConfig()
        self.crawler = CrawlerConfig()

        logger.info(f"Tracking enabled: {self.tracking.tracking_enabled}")


@lru_cache
def get_config() -> Config:
    """Get cached configuration instance"""
    return Config()


# Global configuration instance
config = get_config()
