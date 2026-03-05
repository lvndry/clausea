from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.core.database import db_dry_run, db_session
from src.core.logging import get_logger, setup_logging
from src.pipeline import DocumentAnalyzer, LegalDocumentPipeline
from src.services.service_factory import create_document_service, create_product_service
from src.summarizer import generate_product_overview, summarize_all_product_documents

logger = get_logger(__name__)
console = Console()


def _render_header() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]Clausea CLI[/bold cyan]\n[dim]Crawl, classify, or run the full pipeline.[/dim]",
            border_style="cyan",
            box=box.ASCII,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clausea CLI")
    parser.add_argument(
        "--action",
        choices=["crawl", "classify", "pipeline"],
        help="Action to run (overrides interactive prompt)",
    )
    parser.add_argument(
        "--products",
        help="Comma-separated product slugs or indexes (e.g. 'notion,figma' or '1,3')",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run on all products",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without persisting DB writes (reads still allowed)",
    )
    return parser.parse_args()


def _prompt_action() -> str:
    table = Table(
        title="Select an action",
        box=box.ASCII,
        header_style="bold cyan",
        show_edge=True,
    )
    table.add_column("Key", justify="right", style="bold")
    table.add_column("Action", style="white")
    table.add_row("1", "Crawl + classify (discover, classify, store legal docs only)")
    table.add_row("2", "Classify only (re-run doc classification)")
    table.add_row("3", "Full pipeline (crawl → summarize → overview)")
    console.print(table)
    choice = Prompt.ask("Select", choices=["1", "2", "3"], default="3")
    return {"1": "crawl", "2": "classify", "3": "pipeline"}[choice]


def _prompt_product_selection(products: list) -> str:
    console.print(
        "[bold]Select products[/bold] (comma-separated indexes or slugs). "
        "Type [cyan]all[/cyan] to run on every product."
    )
    table = Table(box=box.ASCII, header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("Product")
    table.add_column("Slug", style="dim")
    for idx, product in enumerate(products, 1):
        name = product.name or product.slug
        table.add_row(str(idx), name, product.slug)
    console.print(table)
    return Prompt.ask("Selection", default="all")


def _select_products(products: list, selection: str, allow_all: bool) -> list:
    if allow_all or selection.lower() in {"all", "*"}:
        return products

    by_slug = {p.slug: p for p in products}
    selected: list = []
    for token in [t.strip() for t in selection.split(",") if t.strip()]:
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(products):
                selected.append(products[idx - 1])
            continue
        if token in by_slug:
            selected.append(by_slug[token])

    # Deduplicate while preserving order
    seen = set()
    unique: list = []
    for product in selected:
        if product.slug not in seen:
            unique.append(product)
            seen.add(product.slug)
    return unique


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}m {s:.1f}s"


async def _run_crawl_only(products: list) -> None:
    logger.info("Starting crawl + classify run", product_count=len(products))
    pipeline = LegalDocumentPipeline()
    start = time.perf_counter()
    with console.status(
        f"[cyan]Crawling & classifying {len(products)} product(s)...[/cyan]", spinner="dots"
    ):
        await pipeline.run(products)
    elapsed = time.perf_counter() - start
    console.print(
        f"[green]Crawl + classify complete[/green] [dim]({_format_duration(elapsed)})[/dim]"
    )


async def _run_classify_only(products: list) -> None:
    logger.info("Starting classify-only run", product_count=len(products))
    analyzer = DocumentAnalyzer()
    async with db_session() as db:
        doc_svc = create_document_service()
        for product in products:
            documents = await doc_svc.get_product_documents(db, product.id)
            logger.info(
                "Classifying documents",
                product_slug=product.slug,
                document_count=len(documents),
            )
            start = time.perf_counter()
            with console.status(
                f"[cyan]Classifying {product.slug} ({len(documents)} docs)...[/cyan]",
                spinner="dots",
            ):
                for doc in documents:
                    if not doc.text:
                        logger.info("Skipping doc without text", document_id=doc.id)
                        continue
                    classification = await analyzer.classify_document(
                        doc.url, doc.text, doc.metadata
                    )
                    is_legal = classification.get("is_legal_document", False)
                    doc.doc_type = classification.get("classification", doc.doc_type)

                    locale = await analyzer.detect_locale(doc.text, doc.metadata, doc.url)
                    doc.locale = locale.get("locale", doc.locale)

                    regions = await analyzer.detect_regions(doc.text, doc.metadata, doc.url)
                    doc.regions = regions.get("regions", doc.regions or [])

                    effective_date_str = await analyzer.extract_effective_date(
                        doc.text, doc.metadata
                    )
                    if effective_date_str:
                        try:
                            doc.effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d")
                        except ValueError:
                            pass

                    title_result = await analyzer.extract_title(
                        doc.markdown, doc.metadata, doc.url, doc.doc_type
                    )
                    if title_result.get("title"):
                        doc.title = title_result["title"]

                    await doc_svc.update_document(db, doc)
                    logger.info(
                        "Document classified",
                        document_id=doc.id,
                        doc_type=doc.doc_type,
                        is_legal=is_legal,
                    )

            elapsed = time.perf_counter() - start
            console.print(
                f"[green]Done:[/green] {product.slug} [dim]({_format_duration(elapsed)})[/dim]"
            )
            logger.info("Classification complete", product_slug=product.slug)


async def _run_full_pipeline(products: list) -> None:
    await _run_crawl_only(products)
    async with db_session() as db:
        product_svc = create_product_service()
        doc_svc = create_document_service()
        for product in products:
            start = time.perf_counter()
            with console.status(f"[cyan]Summarizing {product.slug}...[/cyan]", spinner="dots"):
                logger.info("Summarizing documents", product_slug=product.slug)
                await summarize_all_product_documents(db, product.slug, doc_svc)
            elapsed = time.perf_counter() - start
            console.print(
                f"[green]Summarize done:[/green] {product.slug} [dim]({_format_duration(elapsed)})[/dim]"
            )

            start = time.perf_counter()
            with console.status(
                f"[cyan]Generating overview for {product.slug}...[/cyan]", spinner="dots"
            ):
                logger.info("Generating overview", product_slug=product.slug)
                await generate_product_overview(
                    db,
                    product.slug,
                    force_regenerate=True,
                    product_svc=product_svc,
                    document_svc=doc_svc,
                )
            elapsed = time.perf_counter() - start
            console.print(
                f"[green]Overview done:[/green] {product.slug} [dim]({_format_duration(elapsed)})[/dim]"
            )


async def _main() -> None:
    setup_logging()
    args = _parse_args()

    _render_header()

    # Determine dry-run: CLI flag takes precedence, otherwise ask interactively
    is_dry_run = args.dry_run
    if not is_dry_run and not args.action:
        is_dry_run = Confirm.ask(
            "Run in [yellow]dry-run[/yellow] mode (no DB writes)?", default=False
        )

    with db_dry_run(is_dry_run):
        async with db_session() as db:
            product_svc = create_product_service()
            products = await product_svc.get_all_products(db)

        products = sorted(products, key=lambda p: (p.slug or "").lower())

        if not products:
            logger.info("No products found in database")
            console.print("[yellow]No products found in database.[/yellow]")
            return

        action = args.action or _prompt_action()
        if action not in {"crawl", "classify", "pipeline"}:
            console.print("[red]Invalid action.[/red]")
            return

        selection = args.products or _prompt_product_selection(products)
        selected_products = _select_products(products, selection, args.all)
        if not selected_products:
            console.print("[red]No products selected.[/red]")
            return

        logger.info(
            "Selected products",
            action=action,
            dry_run=is_dry_run,
            products=[p.slug for p in selected_products],
        )

        dry_run_label = (
            "\n[bold yellow]Mode:[/bold yellow] DRY RUN (no DB writes)" if is_dry_run else ""
        )
        console.print(
            Panel.fit(
                f"[bold]Action:[/bold] {action}\n[bold]Products:[/bold] "
                f"{', '.join(p.slug for p in selected_products)}{dry_run_label}",
                border_style="green" if not is_dry_run else "yellow",
                box=box.ASCII,
            )
        )

        if action == "crawl":
            await _run_crawl_only(selected_products)
        elif action == "classify":
            await _run_classify_only(selected_products)
        else:
            await _run_full_pipeline(selected_products)

        logger.info("CLI run complete", action=action, dry_run=is_dry_run)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
