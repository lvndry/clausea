from __future__ import annotations

import asyncio
import concurrent.futures
import time
from datetime import datetime
from pathlib import Path
from threading import Event

import streamlit as st

from src.core.config import config
from src.dashboard.db_utils import get_all_products_isolated
from src.dashboard.utils import run_async, suppress_streamlit_warnings
from src.models.product import Product
from src.pipeline import LegalDocumentPipeline, ProcessingStats


def get_log_file_path(product: Product) -> Path:
    """Generate the log file path for a product crawl (matching the format used in LegalDocumentPipeline)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{timestamp}_{product.slug}_crawl.log"
    return Path("logs") / log_filename


def find_most_recent_log_file(product: Product) -> Path | None:
    """Find the most recent log file for a product."""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return None

    # Find all log files for this product
    pattern = f"*_{product.slug}_crawl.log"
    log_files = list(logs_dir.glob(pattern))

    if not log_files:
        return None

    # Return the most recently modified file
    return max(log_files, key=lambda p: p.stat().st_mtime)


def read_log_file(log_file_path: Path | None) -> str:
    """Read the contents of a log file if it exists."""
    if not log_file_path or not log_file_path.exists():
        return ""
    try:
        return log_file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading log file: {str(e)}"


def read_log_file_tail(
    log_file_path: Path | None, last_position: int = 0, max_lines: int = 1000
) -> tuple[str, int]:
    """Read new content from a log file since last position (tail-like behavior).

    Limits output to the last max_lines to prevent exceeding maximum call size.

    Args:
        log_file_path: Path to the log file
        last_position: Last known position in the file
        max_lines: Maximum number of lines to return (default: 1000)

    Returns:
        Tuple of (new_content, new_position)
    """
    if not log_file_path or not log_file_path.exists():
        return "", last_position

    try:
        with open(log_file_path, encoding="utf-8") as f:
            f.seek(last_position)
            new_content = f.read()
            new_position = f.tell()

            # Limit to last max_lines to prevent exceeding maximum call size
            if new_content:
                lines = new_content.splitlines(keepends=True)
                if len(lines) > max_lines:
                    # Keep only the last max_lines
                    new_content = "".join(lines[-max_lines:])
                    # Update position to reflect we're only keeping tail
                    # This ensures we don't skip content on next read
                    # but we'll handle truncation at display level
                    new_position = f.tell()

            return new_content, new_position
    except Exception as e:
        return f"Error reading log file: {str(e)}", last_position


def run_crawl_async(product: Product, stop_event: Event | None = None):
    """Run crawling using LegalDocumentPipeline in a dedicated event loop."""

    def run_in_thread():
        # Suppress Streamlit ScriptRunContext warnings in worker threads
        with suppress_streamlit_warnings():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def runner():
                pipeline = LegalDocumentPipeline(
                    max_depth=config.crawler.max_depth,
                    max_pages=config.crawler.max_pages,
                    crawler_strategy="bfs",
                    concurrent_limit=5,  # Reduced for single product
                    delay_between_requests=1.0,
                )

                monitor_task: asyncio.Task | None = None
                if stop_event is not None:

                    async def monitor_stop_signal() -> None:
                        while not stop_event.is_set():
                            await asyncio.sleep(0.2)

                try:
                    return await pipeline.run([product])
                finally:
                    if monitor_task:
                        monitor_task.cancel()
                        try:
                            await monitor_task
                        except asyncio.CancelledError:
                            pass

            try:
                return loop.run_until_complete(runner())
            except Exception as e:
                st.error(f"Crawling operation failed: {str(e)}")
                return {}

    return run_in_thread()


def run_crawl_all_products_async(products: list[Product], max_parallel: int = 2):
    """Run crawling for all products with optional parallelization

    Args:
        products: List of products to crawl
        max_parallel: Maximum number of products to crawl in parallel (default: 2)

    Returns:
        Dictionary mapping product slugs to their processing stats (or None if failed)
    """
    results = {}

    def run_in_thread():
        with suppress_streamlit_warnings():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use semaphore to limit parallel execution
                semaphore = asyncio.Semaphore(max_parallel)

                async def crawl_with_semaphore(
                    product: Product,
                ):
                    async with semaphore:
                        try:
                            pipeline = LegalDocumentPipeline(
                                max_depth=config.crawler.max_depth,
                                max_pages=config.crawler.max_pages,
                                crawler_strategy="bfs",
                                concurrent_limit=5,
                                delay_between_requests=1.0,
                            )
                            # Process single product - returns list[Document]
                            documents = await pipeline._process_product(product)
                            # Create a minimal ProcessingStats for single product
                            return product.slug, ProcessingStats(
                                products_processed=1,
                                products_failed=0,
                                failed_product_slugs=[],
                                legal_documents_stored=len(documents) if documents else 0,
                            )
                        except Exception as e:
                            # Log error but don't use st.error in thread context
                            from src.core.logging import get_logger

                            logger = get_logger(__name__)
                            logger.error(f"Error crawling {product.name}: {str(e)}")
                            return product.slug, None

                # Create tasks for all products
                tasks = [crawl_with_semaphore(product) for product in products]
                # Run all tasks
                crawl_results = loop.run_until_complete(asyncio.gather(*tasks))

                # Convert results to dictionary
                for slug, stats in crawl_results:
                    results[slug] = stats

                return results
            finally:
                # CRITICAL: Wait until ALL tasks are truly complete before closing the loop
                # This includes all database operations that may be pending
                max_wait_seconds = 2  # Reduced from 10
                wait_interval = 0.1
                max_iterations = int(max_wait_seconds / wait_interval)

                for _ in range(max_iterations):
                    # Get all pending tasks
                    all_tasks = asyncio.all_tasks(loop)
                    pending_tasks = [
                        t for t in all_tasks if not t.done() and t is not asyncio.current_task(loop)
                    ]

                    if not pending_tasks:
                        break

                    # Wait for pending tasks to complete
                    try:
                        loop.run_until_complete(asyncio.wait(pending_tasks, timeout=wait_interval))
                    except Exception:
                        pass

                # Final verification: ensure no tasks remain
                final_tasks = [
                    t
                    for t in asyncio.all_tasks(loop)
                    if not t.done() and t is not asyncio.current_task(loop)
                ]
                if final_tasks:
                    # Force wait for any remaining tasks with a small timeout
                    loop.run_until_complete(asyncio.wait(final_tasks, timeout=1.0))

                # Only close the loop after we've verified all tasks are complete
                # Shutdown async generators first
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass

                # Close the loop - all operations should be complete by now
                loop.close()

    # Run in a separate thread
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        try:
            return future.result()
        except Exception as e:
            st.error(f"Crawling operation failed: {str(e)}")
            return {}


def show_crawling() -> None:
    # Title with refresh button
    col_title, col_refresh = st.columns([10, 1])
    with col_title:
        st.title("🕷️ Start Crawling")
    with col_refresh:
        if st.button("🔄", help="Refresh products list", key="refresh_products_btn"):
            st.session_state["refresh_products_crawling"] = True
            st.rerun()

    # Cache products in session state to avoid re-fetching on every rerun
    # This prevents DB reconnection when the crawl button is clicked
    cache_key = "cached_products_for_crawling"
    refresh_key = "refresh_products_crawling"

    # Check if we need to refresh products
    if refresh_key not in st.session_state:
        st.session_state[refresh_key] = False

    # Fetch products only if not cached or if refresh was requested
    if cache_key not in st.session_state or st.session_state[refresh_key]:
        products = run_async(get_all_products_isolated())
        if products is not None:
            st.session_state[cache_key] = products
        st.session_state[refresh_key] = False
    else:
        products = st.session_state[cache_key]

    if products is None:
        st.error("Failed to load products from database")
        return

    if not products:
        st.warning("No products found. Please create a product first.")
        return

    # Filter products that have either crawl_base_urls or domains
    products_with_urls = [p for p in products if p.crawl_base_urls or p.domains]

    if not products_with_urls:
        st.warning(
            "No products have crawl base URLs or domains configured. "
            "Please add crawl URLs or domains to at least one product."
        )
        return

    # Create product dropdown options
    product_options = {
        f"{product.name} ({product.slug})": product for product in products_with_urls
    }

    # Check if a product was preselected (from session state)
    preselected_product = st.session_state.get("selected_product_for_crawl", None)
    default_index = 0

    if preselected_product:
        # Find the index of the preselected product
        for i, product in enumerate(products_with_urls):
            if product.id == preselected_product:
                default_index = i
                break

    selected_product_key = st.selectbox(
        "Select Product to Crawl",
        options=list(product_options.keys()),
        index=default_index,
        help="Choose which product you want to crawl for legal documents",
    )

    selected_product = product_options[selected_product_key]

    # Show product details
    st.write("---")
    st.subheader(f"Product Details: {selected_product.name}")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Domains:**")
        for domain in selected_product.domains:
            st.write(f"• {domain}")

    with col2:
        st.write("**Crawl Base URLs:**")
        if selected_product.crawl_base_urls:
            for url in selected_product.crawl_base_urls:
                st.write(f"• [{url}]({url})")
        elif selected_product.domains:
            # Show domains that will be used as fallback
            for domain in selected_product.domains:
                url = (
                    f"https://{domain}"
                    if not domain.startswith(("http://", "https://"))
                    else domain
                )
                st.write(f"• [{url}]({url}) (from domain)")
        else:
            st.write("• No crawl URLs configured")

    st.write("**Categories:**")
    st.write(
        ", ".join(selected_product.categories) if selected_product.categories else "No categories"
    )

    # Crawling section
    st.write("---")
    st.subheader("Start Crawling")

    # Single product crawling section
    st.info(f"""
    **Single Product:**
    • Crawl the base URLs for {selected_product.name}
    • Find and classify legal documents
    • Store discovered documents in the database
    • This process may take several minutes
    """)

    # Initialize crawl session state
    crawl_key = f"crawl_{selected_product.slug}"
    if crawl_key not in st.session_state:
        st.session_state[crawl_key] = {
            "running": False,
            "future": None,
            "executor": None,
            "log_path": None,
            "log_position": 0,
            "log_content": "",
            "stats": None,
            "stop_event": None,
            "stop_requested": False,
            "cancelled": False,
        }

    crawl_state = st.session_state[crawl_key]

    # Start crawling button for single product
    if st.button("🚀 Start Crawling", type="primary", key="start_crawl_btn"):
        # Clear any previous crawl session state
        if "selected_product_for_crawl" in st.session_state:
            del st.session_state["selected_product_for_crawl"]

        # Determine log file path before starting (using same format as crawler)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{timestamp}_{selected_product.slug}_crawl.log"
        expected_log_path = Path("logs") / log_filename

        # Initialize crawl state
        crawl_state["running"] = True
        crawl_state["log_path"] = str(expected_log_path)
        crawl_state["log_position"] = 0
        crawl_state["log_content"] = ""
        crawl_state["stats"] = None
        crawl_state["stop_event"] = Event()
        crawl_state["stop_requested"] = False
        crawl_state["cancelled"] = False

        # Start crawling in a thread (don't use context manager to keep executor alive)
        executor = concurrent.futures.ThreadPoolExecutor()
        future = executor.submit(
            run_crawl_async,
            selected_product,
            crawl_state["stop_event"],
        )
        crawl_state["future"] = future
        crawl_state["executor"] = executor  # Keep executor reference

    # Display crawl status and logs if crawl is running or was started
    if crawl_state.get("running") or crawl_state.get("future"):
        # Check if crawl is still running
        if crawl_state.get("future") and not crawl_state["future"].done():
            stop_disabled = crawl_state.get("stop_requested", False)
            if st.button(
                "⏹ Stop Crawling",
                type="secondary",
                disabled=stop_disabled,
                key=f"stop_crawl_btn_{selected_product.slug}",
            ):
                if crawl_state.get("stop_event"):
                    crawl_state["stop_event"].set()
                    crawl_state["stop_requested"] = True
            if crawl_state.get("stop_requested"):
                st.info("Stop requested. Finishing current tasks safely...")

            # Poll for logs
            log_path = Path(crawl_state["log_path"]) if crawl_state.get("log_path") else None
            if log_path and log_path.exists():
                new_content, new_position = read_log_file_tail(
                    log_path, crawl_state["log_position"], max_lines=1000
                )
                if new_content:
                    # Accumulate new content
                    crawl_state["log_content"] += new_content
                    # Keep only last 1000 lines to prevent exceeding maximum call size
                    all_lines = crawl_state["log_content"].splitlines(keepends=True)
                    if len(all_lines) > 1000:
                        crawl_state["log_content"] = "".join(all_lines[-1000:])
                    crawl_state["log_position"] = new_position

            # Use status for better control over display
            with st.status(
                f"🕷️ Crawling {selected_product.name}... This may take several minutes.",
                expanded=True,
            ) as status:
                st.write("🔍 Crawler is running...")

                # Display logs
                if crawl_state["log_content"]:
                    st.write("---")
                    st.subheader("📋 Crawler Logs (Live)")
                    if log_path:
                        st.caption(f"Log file: `{log_path}`")
                    st.code(crawl_state["log_content"], language="text")
                else:
                    st.info("📝 Waiting for logs to appear...")

            # Rerun to update logs (with a small delay to avoid too frequent updates)
            time.sleep(0.5)
            st.rerun()

        else:
            # Crawl completed, get final result
            if crawl_state.get("future"):
                try:
                    crawl_state["stats"] = crawl_state["future"].result()
                except asyncio.CancelledError:
                    crawl_state["stats"] = None
                    crawl_state["cancelled"] = True
                    st.warning(f"Crawling for {selected_product.name} was cancelled.")
                except Exception as e:
                    crawl_state["stats"] = None
                    st.error(f"Crawling error: {str(e)}")
                finally:
                    # Clean up executor
                    if "executor" in crawl_state:
                        crawl_state["executor"].shutdown(wait=False)
                        del crawl_state["executor"]
                    crawl_state["stop_event"] = None
                    crawl_state["running"] = False
                    crawl_state["future"] = None

            # Read final log content (limit to last 1000 lines)
            log_path = Path(crawl_state["log_path"]) if crawl_state.get("log_path") else None
            if log_path and log_path.exists():
                final_content = read_log_file(log_path)
                if final_content:
                    # Keep only last 1000 lines to prevent exceeding maximum call size
                    lines = final_content.splitlines(keepends=True)
                    if len(lines) > 1000:
                        crawl_state["log_content"] = "".join(lines[-1000:])
                    else:
                        crawl_state["log_content"] = final_content

            # Show final status
            status_label: str
            status_state: str
            if crawl_state.get("cancelled"):
                status_label = f"🛑 Crawling {selected_product.name} was stopped"
                status_state = "error"
            elif crawl_state["stats"] is not None:
                status_label = f"✅ Crawling {selected_product.name} completed!"
                status_state = "complete"
            else:
                status_label = f"❌ Crawling {selected_product.name} failed"
                status_state = "error"

            with st.status(status_label, expanded=False, state=status_state) as status:
                if crawl_state["log_content"]:
                    st.write("---")
                    st.subheader("📋 Crawler Logs")
                    if log_path:
                        st.caption(f"Log file: `{log_path}`")
                    with st.expander("View full crawler logs", expanded=True):
                        st.code(crawl_state["log_content"], language="text")

            # Show results
            if crawl_state.get("cancelled"):
                st.warning(
                    "Crawling was stopped before completion. Partial results may be available."
                )
            elif crawl_state["stats"] is not None:
                st.success("✅ Crawling completed successfully!")
                if crawl_state["stats"].legal_documents_stored > 0:
                    st.write(
                        f"**Found {crawl_state['stats'].legal_documents_stored} legal documents.**"
                    )
                else:
                    st.warning("No legal documents were found during the crawl.")
                    with st.expander("Possible reasons:"):
                        st.write("• The websites don't have legal documents")
                        st.write("• The documents aren't accessible")
                        st.write("• The classification didn't identify them as legal documents")
            else:
                st.error("Crawling failed. Please check the logs and try again.")

            # Clear crawl state after showing results
            if crawl_key in st.session_state:
                del st.session_state[crawl_key]

    # All products crawling section
    st.write("---")
    st.subheader("Crawl All Products")

    st.info(f"""
    **All Products ({len(products_with_urls)} products):**
    • Crawl all products with crawl URLs configured
    • Process up to 2 products in parallel
    • This process may take a long time
    """)

    # Start crawling all products button
    if st.button("🚀 Crawl All Products", type="secondary", key="start_crawl_all_btn"):
        # Start crawling all products
        with st.status(
            f"🕷️ Crawling {len(products_with_urls)} products... This may take a very long time.",
            expanded=True,
        ) as status:
            # Show progress info
            st.write(f"🔍 Starting crawler for {len(products_with_urls)} products...")

            # Run the crawling process for all products
            results = run_crawl_all_products_async(products_with_urls, max_parallel=2)

            if results:
                successful = sum(1 for stats in results.values() if stats is not None)
                status.update(
                    label=f"✅ Crawling completed! {successful}/{len(results)} products processed.",
                    state="complete",
                    expanded=False,
                )
            else:
                status.update(label="❌ Crawling all products failed", state="error")

        if results:
            # Show results summary
            successful = sum(1 for stats in results.values() if stats is not None)
            failed = len(results) - successful
            total_docs = sum(
                stats.legal_documents_stored for stats in results.values() if stats is not None
            )

            if successful > 0:
                st.success(f"✅ Crawling completed! {successful} products processed successfully.")
                st.write(f"**Total legal documents found: {total_docs}**")

                if failed > 0:
                    st.warning(f"⚠️ {failed} products failed to crawl.")

                # Show detailed results
                with st.expander("View detailed results"):
                    for product in products_with_urls:
                        stats = results.get(product.slug)
                        if stats is not None:
                            st.write(
                                f"✅ **{product.name}**: {stats.legal_documents_stored} documents"
                            )
                        else:
                            st.write(f"❌ **{product.name}**: Failed")
            else:
                st.error("All products failed to crawl. Please check the logs and try again.")
        else:
            st.error("Crawling operation failed to return results.")

    # Back to products button
    st.write("---")
    if st.button("← Back to Products", key="back_to_products"):
        # Clear crawl session state and navigate back
        if "selected_product_for_crawl" in st.session_state:
            del st.session_state["selected_product_for_crawl"]
        st.session_state["current_page"] = "view_products"
        st.rerun()
