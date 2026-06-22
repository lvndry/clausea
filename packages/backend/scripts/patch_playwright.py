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

Fixed upstream in camoufox >0.4.11. This script patches the bundled file
until the project upgrades to a fixed release.

Run during Docker image build (after the venv is copied into the image).
Exits non-zero if coreBundle.js is not found so the build fails loudly.
Logs a warning (but does NOT fail) when a pattern is absent — this means the
file was already patched by a prior layer or a fixed upstream was installed.
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
    for old, new in PATCHES:
        count = patched.count(old)
        if count == 0:
            print(f"  WARNING: pattern not found (already patched or version changed): {old!r}")
            continue
        patched = patched.replace(old, new)
        print(f"  Replaced {count}x: {old!r}")
        total_replaced += count

    if total_replaced == 0:
        print(
            f"Playwright patch: nothing to do in {path} (all patterns absent — likely already applied)"
        )
        return

    with open(path, "w", encoding="utf-8") as f:
        f.write(patched)

    print(
        f"Playwright patch applied to {path} ({total_replaced} replacement(s) across {len(PATCHES)} pattern(s))"
    )


if __name__ == "__main__":
    main()
