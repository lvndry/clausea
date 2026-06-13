"""Diagnostic: probe the headless browser against a control page and Duolingo /privacy.

Prints per-load-state timings so we can see WHERE navigation hangs.
"""

from __future__ import annotations

import asyncio
import time

from camoufox import AsyncCamoufox


async def probe(context, url: str) -> None:
    page = await context.new_page()
    t0 = time.perf_counter()
    print(f"\n=== {url} ===")
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        print(
            f"  goto(domcontentloaded): {time.perf_counter() - t0:.1f}s  status={resp.status if resp else None}"
        )
    except Exception as e:
        print(
            f"  goto FAILED after {time.perf_counter() - t0:.1f}s: {type(e).__name__}: {str(e)[:120]}"
        )
        await page.close()
        return
    for state in ("load", "networkidle"):
        ts = time.perf_counter()
        try:
            await page.wait_for_load_state(state, timeout=15000)
            print(f"  {state}: +{time.perf_counter() - ts:.1f}s")
        except Exception as e:
            print(f"  {state}: TIMEOUT +{time.perf_counter() - ts:.1f}s ({str(e)[:60]})")
    html = await page.content()
    import re

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    print(f"  rendered_html={len(html)} visible_text={len(text)}")
    low = html.lower()
    print(
        f"  recaptcha={'recaptcha' in low} onetrust={'onetrust' in low or 'cookielaw' in low} "
        f"challenge={'challenge' in low or 'captcha' in low}"
    )
    print(f"  text_sample: {text[:240]}")
    await page.close()


async def main() -> None:
    t0 = time.perf_counter()
    async with AsyncCamoufox(headless=True) as context:
        print(f"browser launched in {time.perf_counter() - t0:.1f}s")
        await probe(context, "https://example.com")
        await probe(context, "https://www.duolingo.com/privacy")


if __name__ == "__main__":
    asyncio.run(main())
