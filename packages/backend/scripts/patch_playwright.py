"""
Patch Playwright's vendored Node.js driver (coreBundle.js).

Camoufox's Juggler can emit Page.uncaughtError without a location field,
causing an uncaught TypeError in _Page.addPageError:
    url: pageError.location.url,   # crashes when location is undefined

Fixed upstream in camoufox >0.4.11. This script patches the bundled file
until the project upgrades to a fixed release.

Run during Docker image build (after the venv is copied into the image).
Exits non-zero if the file or pattern is not found so the build fails loudly.
"""

import glob
import sys


def main() -> None:
    matches = glob.glob(
        "/opt/venv/lib/python*/site-packages/playwright/driver/package/lib/coreBundle.js"
    )
    if not matches:
        sys.exit("ERROR: coreBundle.js not found — update the patch path")

    path = matches[0]
    old = "url: pageError.location.url,"
    new = 'url: pageError.location ? pageError.location.url : "",'

    src = path.read_text() if hasattr(path, "read_text") else open(path).read()
    if old not in src:
        sys.exit(
            f"ERROR: patch pattern not found in {path} — already fixed upstream or version changed"
        )

    patched = src.replace(old, new)
    with open(path, "w") as f:
        f.write(patched)

    count = patched.count(new)
    print(f"Playwright patch applied to {path} ({count} occurrence(s))")


if __name__ == "__main__":
    main()
