"""Shared headless-browser lifecycle management.

A single Camoufox/Firefox instance is shared by every crawler in the process.
Keyed by the running event loop so asyncio primitives bind correctly.
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
