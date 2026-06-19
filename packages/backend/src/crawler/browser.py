"""Shared headless-browser lifecycle management for SPA/hydration-dependent pages.

**What it does**
Maintains a single ``AsyncCamoufox`` (Firefox) instance per running event loop.
When ``ClauseaCrawler`` encounters a page that appears to be a JavaScript SPA
(empty or very short text body after static fetch), it launches the browser,
navigates, waits for network-idle, and re-extracts the page text after JS
hydration.  The browser is lazy-started on first use and persisted across
multiple URLs within the same crawl.

**What it contains**
- ``setup_browser()``: creates and returns an ``AsyncCamoufox`` context manager.
- ``cleanup_browser()``: tears down the shared instance (called at crawl end).
- ``_shared_browser_instances``, ``_shared_browser_contexts``: module-level dicts
  keyed by event-loop id.
- ``_shared_browser_locks``, ``_global_browser_semaphores``: asyncio primitives
  for safe concurrent access to the shared instance.
- ``_block_heavy_assets(route, request)``: CDP route handler that blocks images,
  fonts, and media from loading inside the browser (saves bandwidth and time).

**What it allows/prevents**
Allows the crawler to extract content from JS-rendered policy pages that would
otherwise appear blank.  Prevents launching a full browser per URL (only one
instance per event loop) and prevents loading of non-essential assets during
rendering.
"""

import asyncio
from typing import Any

from camoufox import AsyncCamoufox
from playwright.async_api import Browser, BrowserContext, Page, Route

from src.core.logging import get_logger
from src.crawler.constants import _BLOCKED_ASSETS_RE, BROWSER_LAUNCH_TIMEOUT_S

logger = get_logger(__name__, component="crawler:browser")

_LoopKey = asyncio.AbstractEventLoop | None
_global_browser_semaphores: dict[_LoopKey, asyncio.Semaphore] = {}
_shared_browser_locks: dict[_LoopKey, asyncio.Lock] = {}
_shared_browser_instances: dict[_LoopKey, AsyncCamoufox] = {}
_shared_browser_contexts: dict[_LoopKey, "Browser | BrowserContext"] = {}


def _running_loop() -> _LoopKey:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def get_global_browser_slot(concurrency: int) -> asyncio.Semaphore:
    loop = _running_loop()
    if loop not in _global_browser_semaphores:
        _global_browser_semaphores[loop] = asyncio.Semaphore(max(1, concurrency))
    return _global_browser_semaphores[loop]


_get_global_browser_slot = get_global_browser_slot


def _get_shared_browser_lock() -> asyncio.Lock:
    loop = _running_loop()
    if loop not in _shared_browser_locks:
        _shared_browser_locks[loop] = asyncio.Lock()
    return _shared_browser_locks[loop]


async def _block_heavy_assets(page: Page) -> None:
    async def _abort(route: Route) -> None:
        try:
            await route.abort()
        except Exception:
            pass

    await page.route(_BLOCKED_ASSETS_RE, _abort)


async def setup_browser(
    proxy: str | None = None, locale: str = "en-US"
) -> tuple[AsyncCamoufox, Browser | BrowserContext]:
    """Launch (once per loop) and return the process-shared Camoufox browser and context."""
    loop = _running_loop()
    async with _get_shared_browser_lock():
        if loop not in _shared_browser_instances:
            init_kwargs: dict[str, Any] = {"headless": True, "locale": locale}
            if proxy:
                init_kwargs["proxy"] = {"server": proxy}

            logger.debug("Launching shared Camoufox browser with kwargs: %s", init_kwargs)
            instance = AsyncCamoufox(**init_kwargs)
            try:
                context = await asyncio.wait_for(
                    instance.__aenter__(), timeout=BROWSER_LAUNCH_TIMEOUT_S
                )
            except Exception:
                logger.error(
                    "Camoufox browser failed to start (launch timeout=%ss)",
                    BROWSER_LAUNCH_TIMEOUT_S,
                    exc_info=True,
                )
                try:
                    await instance.__aexit__(None, None, None)
                except Exception:
                    pass
                raise
            _shared_browser_instances[loop] = instance
            _shared_browser_contexts[loop] = context
            logger.debug("Shared Camoufox launched: context=%r", context)

        return _shared_browser_instances[loop], _shared_browser_contexts[loop]


async def cleanup_browser() -> None:
    """Tear down the shared Camoufox so it relaunches next use."""
    loop = _running_loop()
    async with _get_shared_browser_lock():
        instance = _shared_browser_instances.get(loop)
        if instance is not None:
            try:
                await instance.__aexit__(None, None, None)
            except Exception:
                logger.warning("Error while closing Camoufox browser", exc_info=True)
            finally:
                _shared_browser_instances.pop(loop, None)
                _shared_browser_contexts.pop(loop, None)
            logger.debug("Shared Camoufox browser closed")
