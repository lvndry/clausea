"""Per-domain rate limiting for concurrent crawling."""

import asyncio
import random
import time
from urllib.parse import urlparse

from src.core.logging import get_logger

logger_rate_limit = get_logger(__name__, component="crawler:rate_limit")


class DomainRateLimiter:
    """Per-domain rate limiter for efficient concurrent crawling."""

    def __init__(self, delay_between_requests: float = 1.0, jitter: float = 0.0) -> None:
        self.delay_between_requests = delay_between_requests
        self.jitter = jitter
        self.domain_locks: dict[str, asyncio.Lock] = {}
        self.domain_last_request: dict[str, float] = {}
        self.lock = asyncio.Lock()

    def _normalize_domain(self, url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    async def rate_limit(self, url: str) -> None:
        domain = self._normalize_domain(url)

        async with self.lock:
            if domain not in self.domain_locks:
                self.domain_locks[domain] = asyncio.Lock()
                self.domain_last_request[domain] = 0.0

        domain_lock = self.domain_locks[domain]

        async with domain_lock:
            last_time = self.domain_last_request[domain]
            elapsed = time.time() - last_time

            if elapsed < self.delay_between_requests:
                base_sleep = self.delay_between_requests - elapsed

                if self.jitter > 0:
                    jitter_amt = random.uniform(-self.jitter, self.jitter)
                    sleep_time = max(0, base_sleep + jitter_amt)

                    if sleep_time > 0:
                        logger_rate_limit.debug(
                            f"rate limiting domain '{domain}': sleeping {sleep_time:.2f}s "
                            f"(base: {base_sleep:.2f}s, jitter: {jitter_amt:+.2f}s)"
                        )
                        await asyncio.sleep(sleep_time)
                else:
                    await asyncio.sleep(base_sleep)

            self.domain_last_request[domain] = time.time()

    def clear_cache(self) -> None:
        self.domain_locks.clear()
        self.domain_last_request.clear()
