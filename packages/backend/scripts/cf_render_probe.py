"""Empirical probe: can Camoufox get through OpenAI's Cloudflare challenge?

Reproduces the crawler's render failure and tests alternative wait strategies,
so a fix is grounded in evidence rather than assumption.
"""

import asyncio
import re
import sys
import time

from camoufox.async_api import AsyncCamoufox

URLS = [
    "https://openai.com/policies/privacy-policy/",
    "https://openai.com/policies/row-terms-of-use/",
]

CHALLENGE_MARKER = re.compile(r"enable javascript and cookies", re.IGNORECASE)


def visible_text_len(html: str) -> int:
    no_scripts = re.sub(r"(?is)<script.*?</script\s*>|<style.*?</style\s*>", "", html)
    text = re.sub(r"(?s)<[^>]+>", " ", no_scripts)
    return len(re.sub(r"\s+", " ", text).strip())


def summarize(html: str) -> str:
    challenged = bool(CHALLENGE_MARKER.search(html))
    has_policy = bool(re.search(r"we collect|you agree|personal data|privacy policy", html, re.I))
    return f"bytes={len(html)} visible_text={visible_text_len(html)} challenge={challenged} policy_text={has_policy}"


async def strategy(context, url: str, label: str, fn) -> None:
    page = await context.new_page()
    await page.set_extra_http_headers({"Accept-Encoding": "gzip, deflate"})
    start = time.monotonic()
    try:
        html = await fn(page, url)
        elapsed = time.monotonic() - start
        print(f"  [{label}] {elapsed:5.1f}s OK  {summarize(html)}")
    except Exception as e:
        elapsed = time.monotonic() - start
        msg = (str(e).splitlines() or [""])[0]
        print(f"  [{label}] {elapsed:5.1f}s FAIL {type(e).__name__}: {msg}")
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def s_current(page, url):
    # Exactly what the crawler does today.
    await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
    return await page.content()


async def s_commit_then_wait(page, url):
    # Commit navigation immediately, then give the CF challenge time to solve + reload.
    await page.goto(url, wait_until="commit", timeout=20_000)
    for _ in range(20):
        await asyncio.sleep(1)
        html = await page.content()
        if not CHALLENGE_MARKER.search(html) and visible_text_len(html) > 500:
            return html
    return await page.content()


async def s_domloaded_long(page, url):
    await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    return await page.content()


async def s_networkidle(page, url):
    await page.goto(url, wait_until="networkidle", timeout=45_000)
    return await page.content()


async def main() -> None:
    async with AsyncCamoufox(headless=True, locale="en-US") as context:
        for url in URLS:
            print(f"\n=== {url} ===")
            await strategy(context, url, "current(domloaded,20s)", s_current)
            await strategy(context, url, "commit+poll(≤20s)", s_commit_then_wait)
            await strategy(context, url, "domloaded(45s)", s_domloaded_long)
            await strategy(context, url, "networkidle(45s)", s_networkidle)


async def concurrency_test() -> None:
    """Distinguish IP-block vs concurrency-starvation: render N OpenAI pages at once."""
    url = "https://openai.com/policies/privacy-policy/"
    for n in (4, 10):
        async with AsyncCamoufox(headless=True, locale="en-US") as context:

            async def one(i):
                page = await context.new_page()
                await page.set_extra_http_headers({"Accept-Encoding": "gzip, deflate"})
                start = time.monotonic()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    html = await page.content()
                    return time.monotonic() - start, visible_text_len(html), False
                except Exception:
                    return time.monotonic() - start, 0, True
                finally:
                    await page.close()

            results = await asyncio.gather(*[one(i) for i in range(n)])
            times = [r[0] for r in results]
            fails = sum(1 for r in results if r[2])
            ok_text = [r[1] for r in results if not r[2]]
            print(
                f"  concurrency={n:2d}: max={max(times):5.1f}s min={min(times):4.1f}s "
                f"fails={fails}/{n} text_ok={sum(1 for t in ok_text if t > 500)}/{len(ok_text)}"
            )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "strategies"
    if mode == "concurrency":
        asyncio.run(concurrency_test())
    elif mode == "strategies":
        asyncio.run(main())
    else:
        raise SystemExit(f"unknown mode {mode!r}; use 'strategies' (default) or 'concurrency'")
