"""Guards the render-time request-routing contract.

A #95 regression registered a catch-all ``page.route("**/*")`` whose handler
called ``continue_()`` on every request, routing the whole page load through the
Python event loop and stalling SPA navigation under worker concurrency. The first
fix then used Playwright glob braces (``{png,jpg}``), which Playwright does not
support — so the route matched nothing and asset blocking silently became a no-op.

These tests pin both halves of the contract: the route pattern actually matches
heavy assets (and only assets, never documents/CSS/JS), and the handler aborts.
"""

import pytest

from src.crawler import _BLOCKED_ASSETS_RE, _block_heavy_assets

ASSET_URLS = [
    "https://x.com/a.png",
    "https://x.com/photo.JPG",
    "https://cdn.x.com/f.woff2",
    "https://x.com/v.mp4",
    "https://x.com/icon.svg?v=3",
    "https://x.com/a.png#frag",
]
NON_ASSET_URLS = [
    "https://x.com/privacy",
    "https://x.com/legal/terms",
    "https://x.com/app.js",
    "https://x.com/styles.css",
    "https://x.com/api/data.json",
    "https://x.com/png-guide",  # 'png' in path but not an extension
]


class _RecordingRoute:
    def __init__(self) -> None:
        self.aborted = False
        self.continued = False

    async def abort(self) -> None:
        self.aborted = True

    async def continue_(self) -> None:
        self.continued = True


class _RecordingPage:
    def __init__(self) -> None:
        self.routes: list[tuple[object, object]] = []

    async def route(self, pattern: object, handler: object) -> None:
        self.routes.append((pattern, handler))


@pytest.mark.parametrize("url", ASSET_URLS)
def test_pattern_matches_heavy_assets(url: str) -> None:
    assert _BLOCKED_ASSETS_RE.search(url)


@pytest.mark.parametrize("url", NON_ASSET_URLS)
def test_pattern_ignores_documents_and_code(url: str) -> None:
    assert not _BLOCKED_ASSETS_RE.search(url)


@pytest.mark.asyncio
async def test_registers_single_non_catch_all_route() -> None:
    page = _RecordingPage()
    await _block_heavy_assets(page)  # type: ignore[arg-type]

    assert len(page.routes) == 1
    pattern, _ = page.routes[0]
    assert pattern is _BLOCKED_ASSETS_RE
    assert pattern != "**/*"


@pytest.mark.asyncio
async def test_handler_aborts_and_never_continues() -> None:
    page = _RecordingPage()
    await _block_heavy_assets(page)  # type: ignore[arg-type]

    _, handler = page.routes[0]
    route = _RecordingRoute()
    await handler(route)  # type: ignore[operator]
    assert route.aborted
    assert not route.continued
