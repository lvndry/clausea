"""
Patch Playwright's vendored Node.js driver (coreBundle.js).

Camoufox's Juggler can emit Page.uncaughtError without a location field,
causing uncaught TypeErrors anywhere coreBundle.js accesses pageError.location:

  url: pageError.location.url,           → crashes when location is undefined
  line: pageError.location.lineNumber,   → same crash on the next property
  column: pageError.location.columnNumber

There are at least two independent call sites that build a location object
from pageError (one in the tracing path, one in the dispatcher path), so all
three properties are replaced at every occurrence.

Fixed upstream in camoufox >0.4.11 (not yet published on PyPI as of 2026-06).
This script patches the bundled file until the project upgrades to a fixed release.

Run during Docker image build (after the venv is copied into the image).
Exits non-zero on any of:
  - coreBundle.js not found
  - partial patch (some patterns found, others missing) → runtime crash guaranteed
  - zero patterns found AND zero patched forms confirmed → Playwright changed formatting
"""

import glob
import sys

PATCHES: list[tuple[str, str]] = [
    (
        "url: pageError.location.url,",
        'url: pageError.location ? pageError.location.url : "",',
    ),
    (
        "line: pageError.location.lineNumber,",
        "line: pageError.location ? pageError.location.lineNumber : 0,",
    ),
    (
        "column: pageError.location.columnNumber",
        "column: pageError.location ? pageError.location.columnNumber : 0",
    ),
]


def warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def main() -> None:
    matches = glob.glob(
        "/opt/venv/lib/python*/site-packages/playwright/driver/package/lib/coreBundle.js"
    )
    if not matches:
        sys.exit("ERROR: coreBundle.js not found — update the patch path")

    path = matches[0]
    with open(path, encoding="utf-8") as f:
        src = f.read()

    patched = src
    total_replaced = 0
    found_patterns = 0
    for old, new in PATCHES:
        count = patched.count(old)
        if count == 0:
            warn(f"pattern not found: {old!r}")
            continue
        patched = patched.replace(old, new)
        print(f"  Replaced {count}x: {old!r}")
        total_replaced += count
        found_patterns += 1

    if total_replaced == 0:
        # All "old" patterns were absent. Either the file was already patched by a
        # prior Docker layer (benign) or Playwright changed its formatting so nothing
        # matched (dangerous — unpatched file that will crash at runtime).
        # Distinguish the two by checking whether the patched forms are present.
        confirmed_patched = sum(1 for _, new in PATCHES if new in src)
        if confirmed_patched == len(PATCHES):
            warn(f"all patterns already patched in {path} — nothing to do")
            return
        sys.exit(
            f"ERROR: None of the {len(PATCHES)} patterns were found, and only "
            f"{confirmed_patched}/{len(PATCHES)} patched forms were confirmed present. "
            "Playwright likely changed its property names or formatting. "
            "Update PATCHES in patch_playwright.py."
        )

    if 0 < found_patterns < len(PATCHES):
        sys.exit(
            f"ERROR: Partial patch — {found_patterns}/{len(PATCHES)} patterns matched. "
            "coreBundle.js will still crash at runtime on unpatched properties. "
            "Check whether Playwright changed its formatting or variable names."
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write(patched)

    print(f"Playwright patch applied to {path} ({total_replaced} replacement(s))")


if __name__ == "__main__":
    main()
