"""
Fetch a real web page and save it as a classification fixture.

Usage:
    python scripts/fetch_fixture.py --url URL --expected DOC_TYPE [--name NAME]

Example:
    python scripts/fetch_fixture.py \
        --url https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement \
        --expected privacy_policy \
        --name github_privacy_policy
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify
from rich.console import Console

console = Console()

# Resolve paths relative to this script's location
SCRIPT_DIR = Path(__file__).parent
FIXTURES_DIR = SCRIPT_DIR.parent / "tests" / "fixtures" / "classification"
DOCS_DIR = FIXTURES_DIR / "docs"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


def _derive_name(url: str) -> str:
    """Auto-derive a fixture name from the URL."""
    parsed = urlparse(url)
    netloc = parsed.netloc
    if netloc.startswith("www."):
        netloc = netloc[4:]
    host = netloc.replace(".", "_").replace("-", "_")
    path = parsed.path.strip("/").replace("/", "_").replace("-", "_").replace(".", "_")
    raw = f"{host}_{path}" if path else host
    # Collapse repeated underscores and trim to a sane length
    name = re.sub(r"_+", "_", raw).strip("_")
    return name[:80]


def _extract_metadata(soup: BeautifulSoup) -> dict[str, str]:
    meta: dict[str, str] = {}

    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        meta["title"] = title_tag.string.strip()

    for name_attr, key in [
        ("description", "description"),
        ("og:description", "og:description"),
        ("og:title", "og:title"),
    ]:
        # <meta name="..."> or <meta property="...">
        tag = soup.find("meta", attrs={"name": name_attr}) or soup.find(
            "meta", attrs={"property": name_attr}
        )
        if tag and tag.get("content"):  # type: ignore[union-attr]
            meta[key] = str(tag["content"]).strip()  # type: ignore[index]

    return meta


def fetch_and_save(url: str, expected_doc_type: str, name: str | None = None) -> Path:
    """Fetch URL, parse, and write fixture JSON. Returns the path written."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    if name is None:
        name = _derive_name(url)

    console.print(f"[cyan]Fetching[/cyan] {url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    with httpx.Client(follow_redirects=True, timeout=30, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

    console.print(f"[green]Got {response.status_code}[/green] ({len(response.content):,} bytes)")

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove navigation, header, footer noise before text extraction
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    markdown = markdownify(str(soup), heading_style="ATX", strip=["script", "style"])
    metadata = _extract_metadata(BeautifulSoup(response.text, "html.parser"))

    fixture = {
        "name": name,
        "url": url,
        "expected_doc_type": expected_doc_type,
        "text": text,
        "markdown": markdown,
        "metadata": metadata,
        "fetched_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    fixture_path = DOCS_DIR / f"{name}.json"
    fixture_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False))
    console.print(f"[green]Saved[/green] {fixture_path}")

    # Update manifest
    _update_manifest(name, fixture_path.relative_to(FIXTURES_DIR).as_posix(), expected_doc_type)

    return fixture_path


def _update_manifest(name: str, relative_file: str, expected_doc_type: str) -> None:
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())
    else:
        manifest = {"fixtures": []}

    # Replace existing entry with the same name, or append
    existing = [f for f in manifest["fixtures"] if f["name"] != name]
    existing.append(
        {
            "name": name,
            "file": relative_file,
            "expected_doc_type": expected_doc_type,
        }
    )
    manifest["fixtures"] = existing

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    console.print(f"[green]Manifest updated[/green] ({len(existing)} fixture(s))")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a web page and save as a classification fixture"
    )
    parser.add_argument("--url", required=True, help="URL to fetch")
    parser.add_argument(
        "--expected", required=True, help="Expected document type (e.g. privacy_policy)"
    )
    parser.add_argument(
        "--name", default=None, help="Fixture name (auto-derived from URL if omitted)"
    )
    args = parser.parse_args()

    try:
        path = fetch_and_save(args.url, args.expected, args.name)
        console.print(f"\n[bold green]Done![/bold green] Fixture saved to [dim]{path}[/dim]")
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]HTTP error {exc.response.status_code}:[/red] {exc.request.url}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
