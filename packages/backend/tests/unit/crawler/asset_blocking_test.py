"""Guards the render-time request-routing contract.

A #95 regression registered a catch-all ``page.route("**/*")`` whose handler
called ``continue_()`` on every request, routing the whole page load through the
Python event loop and stalling SPA navigation under worker concurrency. These
tests pin the contract that prevents it: only narrow asset globs are intercepted,
nothing is a catch-all, and the handler aborts (never continues).
"""

import pytest

from src.crawler import _BLOCKED_ASSET_GLOBS, _block_heavy_assets


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
        self.routes: list[tuple[str, object]] = []

    async def route(self, glob: str, handler: object) -> None:
        self.routes.append((glob, handler))


@pytest.mark.asyncio
async def test_blocks_only_narrow_asset_globs_never_catch_all() -> None:
    page = _RecordingPage()
    await _block_heavy_assets(page)  # type: ignore[arg-type]

    registered = [glob for glob, _ in page.routes]
    assert registered == list(_BLOCKED_ASSET_GLOBS)
    assert "**/*" not in registered
    assert all(glob.startswith("**/*.") for glob in registered)


@pytest.mark.asyncio
async def test_handler_aborts_and_never_continues() -> None:
    page = _RecordingPage()
    await _block_heavy_assets(page)  # type: ignore[arg-type]

    for _, handler in page.routes:
        route = _RecordingRoute()
        await handler(route)  # type: ignore[operator]
        assert route.aborted
        assert not route.continued
