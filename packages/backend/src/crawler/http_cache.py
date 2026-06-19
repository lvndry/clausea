"""Conditional-GET cache + async-aware log handler for crawl HTTP traffic.

**What it does**
Wraps ``aiohttp.ClientSession.get`` so that every outgoing request carries
``If-None-Match`` and/or ``If-Modified-Since`` headers from the previous
response to that URL.  When the server replies 304, the cached response body
is returned instead of re-downloading.  The cache is an LRU dict (``OrderedDict``)
bounded at 8192 entries.

**What it contains**
- ``HTTPCache``: the cache dict + ``get`` / ``put`` / ``check`` methods.
- ``AsyncFileLogHandler``: a ``logging.Handler`` that writes log records to a file
  via a ``ThreadPoolExecutor`` so the event loop is never blocked on I/O.
- ``_fetch_with_cache(session, url, headers, cache)``: the core conditional-GET wrapper.

**What it allows/prevents**
Allows the crawler to re-crawl known URLs cheaply (body is preserved across
runs within the same process).  Prevents redundant bandwidth usage and
unnecessary load on target origins for unchanged pages.
"""

import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import aiohttp


class HTTPCache:
    """HTTP response cache for ETag and Last-Modified headers."""

    def __init__(self, max_cache_size: int = 10000):
        self.cache: OrderedDict[str, dict[str, str]] = OrderedDict()
        self.max_cache_size = max_cache_size

    def get_cache_headers(self, url: str) -> dict[str, str]:
        if url not in self.cache:
            return {}

        cache_entry = self.cache[url]
        headers = {}

        if "etag" in cache_entry:
            headers["If-None-Match"] = cache_entry["etag"]
        if "last_modified" in cache_entry:
            headers["If-Modified-Since"] = cache_entry["last_modified"]

        return headers

    def update_cache(self, url: str, response: aiohttp.ClientResponse) -> None:
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")

        if not etag and not last_modified:
            return

        if len(self.cache) >= self.max_cache_size:
            self.cache.popitem(last=False)

        cache_entry: dict[str, str] = {}
        if etag:
            cache_entry["etag"] = etag
        if last_modified:
            cache_entry["last_modified"] = last_modified

        if url in self.cache:
            del self.cache[url]

        self.cache[url] = cache_entry

    def clear_cache(self) -> None:
        self.cache.clear()


class AsyncFileLogHandler(logging.Handler):
    """Async logging handler that writes to file in a thread pool (fire-and-forget)."""

    def __init__(self, file_handler: logging.FileHandler, executor: ThreadPoolExecutor):
        super().__init__()
        self.file_handler = file_handler
        self.executor = executor
        self._shutdown = False

    def set_shutdown(self, shutdown: bool = True) -> None:
        self._shutdown = shutdown

    def emit(self, record: logging.LogRecord) -> None:
        if self._shutdown:
            return

        try:
            self.executor.submit(self.file_handler.emit, record)
        except RuntimeError as e:
            if "cannot schedule new futures after shutdown" in str(e):
                self._shutdown = True
                return
            raise
        except Exception:
            pass
