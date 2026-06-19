"""HTTP response cache (ETag/Last-Modified) and async file logging."""

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
