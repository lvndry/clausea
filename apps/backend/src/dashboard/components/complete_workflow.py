"""Complete A to Z workflow component: Crawling -> Summarization -> Overview."""

import asyncio
import concurrent.futures
import time
from datetime import datetime
from pathlib import Path
from threading import Event

import streamlit as st

from src.dashboard.db_utils import (
    get_all_products_isolated,
    get_dashboard_db,
    get_product_documents_isolated,
)
from src.dashboard.utils import run_async, suppress_streamlit_warnings
from src.models.product import Product
from src.pipeline import LegalDocumentPipeline, ProcessingStats
from src.services.service_factory import create_document_service, create_product_service
from src.summarizer import generate_product_overview, summarize_all_product_documents


def get_log_file_path(product: Product) -> Path:
    """Generate the log file path for a product crawl."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{timestamp}_{product.slug}_crawl.log"
    return Path("logs") / log_filename


def read_log_file_tail(
    log_file_path: Path | None, last_position: int = 0, max_lines: int = 1000
) -> tuple[str, int]:
    """Read new content from a log file since last position (tail-like behavior)."""
    if not log_file_path or not log_file_path.exists():
        return "", last_position

    try:
        with open(log_file_path, encoding="utf-8") as f:
            f.seek(last_position)
            new_content = f.read()
            new_position = f.tell()

            # Limit to last max_lines
            if new_content:
                lines = new_content.splitlines(keepends=True)
                if len(lines) > max_lines:
                    new_content = "".join(lines[-max_lines:])
                    new_position = f.tell()

            return new_content, new_position
    except Exception as e:
        return f"Error reading log file: {str(e)}", last_position


def run_crawl_async(product: Product, stop_event: Event | None = None) -> ProcessingStats | None:
    """Run crawling using LegalDocumentPipeline in a dedicated event loop."""

    def run_in_thread():
        with suppress_streamlit_warnings():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def runner():
                pipeline = LegalDocumentPipeline(
                    max_depth=4,
                    max_pages=500,
                    crawler_strategy="bfs",
                    concurrent_limit=5,
                    delay_between_requests=1.0,
                )

                monitor_task: asyncio.Task | None = None
                if stop_event is not None:

                    async def monitor_stop_signal(event: Event) -> None:
                        while not event.is_set():
                            await asyncio.sleep(0.2)

                    monitor_task = asyncio.create_task(monitor_stop_signal(stop_event))

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
                return None
            finally:
                loop.close()

    return run_in_thread()


async def run_summarization_async_internal(product_slug: str) -> bool:
    """Run document summarization in an isolated async context."""
    try:
        db = await get_dashboard_db()
        document_svc = create_document_service()
        await summarize_all_product_documents(db.db, product_slug, document_svc)
        return True
    except Exception as e:
        st.error(f"Summarization error: {str(e)}")
        return False


def run_summarization_async(
    product_slug: str, loop: asyncio.AbstractEventLoop | None = None
) -> bool:
    """Run document summarization in an isolated async context."""
    try:
        should_close_loop = False
        if loop is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            should_close_loop = True

        try:
            return loop.run_until_complete(run_summarization_async_internal(product_slug))
        finally:
            if should_close_loop:
                pending_tasks = asyncio.all_tasks(loop)
                if pending_tasks:
                    for task in pending_tasks:
                        task.cancel()
                    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                loop.close()
    except Exception as e:
        st.error(f"Summarization error: {str(e)}")
        return False


async def run_overview_async_internal(product_slug: str) -> bool:
    """Run overview generation in an isolated async context."""
    try:
        db = await get_dashboard_db()
        product_svc = create_product_service()
        document_svc = create_document_service()
        await generate_product_overview(
            db.db,
            product_slug,
            force_regenerate=True,
            product_svc=product_svc,
            document_svc=document_svc,
        )
        return True
    except Exception as e:
        st.error(f"Overview generation error: {str(e)}")
        return False


def run_overview_async(product_slug: str, loop: asyncio.AbstractEventLoop | None = None) -> bool:
    """Run overview generation in an isolated async context."""
    try:
        should_close_loop = False
        if loop is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            should_close_loop = True

        try:
            return loop.run_until_complete(run_overview_async_internal(product_slug))
        finally:
            if should_close_loop:
                pending_tasks = asyncio.all_tasks(loop)
                if pending_tasks:
                    for task in pending_tasks:
                        task.cancel()
                    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                loop.close()
    except Exception as e:
        st.error(f"Overview generation error: {str(e)}")
        return False


def show_complete_workflow() -> None:
    """Show the complete A to Z workflow page."""
    st.title("🚀 Complete Workflow: Crawl → Summarize → Overview")

    st.info("""
    **This workflow will:**
    1. **Crawl** - Discover and store legal documents for the product
    2. **Summarize** - Analyze each document for privacy practices
    3. **Overview** - Generate a comprehensive product overview

    This process may take 10-30 minutes depending on the number of documents.
    """)

    # Get all products
    products = run_async(get_all_products_isolated())

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
    preselected_product = st.session_state.get("selected_product_for_workflow", None)
    default_index = 0

    if preselected_product:
        # Find the index of the preselected product
        for i, product in enumerate(products_with_urls):
            if product.id == preselected_product:
                default_index = i
                break

    selected_product_key = st.selectbox(
        "Select Product for Complete Workflow",
        options=list(product_options.keys()),
        index=default_index,
        help="Choose which product to process through the complete workflow",
    )

    selected_product = product_options[selected_product_key]

    # Show product details
    st.write("---")
    st.subheader(f"Product Details: {selected_product.name}")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Domains:**")
        if selected_product.domains:
            for domain in selected_product.domains:
                st.write(f"• {domain}")
        else:
            st.write("• No domains configured")

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

    # Check current status
    st.write("---")
    st.subheader("📊 Current Status")

    documents = run_async(get_product_documents_isolated(selected_product.slug))

    # Ensure documents is always a list
    if documents is None:
        documents = []

    analyzed_count = 0
    for doc in documents:
        if hasattr(doc, "analysis") and doc.analysis:
            analyzed_count += 1

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Documents Found", len(documents))
    with col2:
        st.metric("Documents Analyzed", analyzed_count)
    with col3:
        st.metric("Pending Analysis", len(documents) - analyzed_count)

    # Check if overview exists
    async def check_overview_exists() -> bool:
        db = await get_dashboard_db()
        product_svc = create_product_service()
        overview = await product_svc.get_product_overview(db.db, selected_product.slug)
        return overview is not None

    overview_exists = run_async(check_overview_exists())

    if overview_exists:
        st.success("✅ Product overview already exists")
    else:
        st.info("ℹ️ Product overview not yet generated")

    # Workflow execution section
    st.write("---")
    st.subheader("🚀 Execute Complete Workflow")

    # Initialize workflow session state
    workflow_key = f"workflow_{selected_product.slug}"
    if workflow_key not in st.session_state:
        st.session_state[workflow_key] = {
            "running": False,
            "current_step": None,
            "step_progress": {},
            "crawl_future": None,
            "crawl_executor": None,
            "crawl_stats": None,
            "log_path": None,
            "log_position": 0,
            "log_content": "",
            "stop_event": None,
            "stop_requested": False,
            "cancelled": False,
        }

    # Initialize batch workflow state
    if "batch_workflow" not in st.session_state:
        st.session_state.batch_workflow = {
            "running": False,
            "current_index": 0,
            "products": [],
            "results": [],
            "stop_requested": False,
            "current_step": None,
        }

    batch_workflow_state = st.session_state.batch_workflow

    workflow_state = st.session_state[workflow_key]

    col1, col2 = st.columns(2)
    with col1:
        # Start workflow button for single product
        if st.button("🚀 Start Complete Workflow", type="primary", key="start_workflow_btn"):
            # Clear any previous workflow session state
            if "selected_product_for_workflow" in st.session_state:
                del st.session_state["selected_product_for_workflow"]

            # Determine log file path before starting
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"{timestamp}_{selected_product.slug}_workflow.log"
            expected_log_path = Path("logs") / log_filename

            # Initialize workflow state
            workflow_state["running"] = True
            workflow_state["current_step"] = "crawling"
            workflow_state["step_progress"] = {
                "crawling": {"status": "running", "message": "Starting crawl..."},
                "summarization": {
                    "status": "pending",
                    "message": "Waiting for crawl to complete...",
                },
                "overview": {
                    "status": "pending",
                    "message": "Waiting for summarization to complete...",
                },
            }
            workflow_state["log_path"] = str(expected_log_path)
            workflow_state["log_position"] = 0
            workflow_state["log_content"] = ""
            workflow_state["crawl_stats"] = None
            workflow_state["stop_event"] = Event()
            workflow_state["stop_requested"] = False
            workflow_state["cancelled"] = False

            # Start crawling in a thread
            executor = concurrent.futures.ThreadPoolExecutor()
            future = executor.submit(
                run_crawl_async,
                selected_product,
                workflow_state["stop_event"],
            )
            workflow_state["crawl_future"] = future
            workflow_state["crawl_executor"] = executor
    with col2:
        # Start workflow button for all products
        if st.button(
            "🔄 Run Workflow for All Products", type="secondary", key="start_batch_workflow_btn"
        ):
            batch_workflow_state["running"] = True
            batch_workflow_state["current_index"] = 0
            batch_workflow_state["products"] = products_with_urls
            batch_workflow_state["results"] = []
            batch_workflow_state["stop_requested"] = False
            batch_workflow_state["current_step"] = (
                f"Starting workflow for {len(products_with_urls)} products..."
            )

    # Display batch workflow progress
    if batch_workflow_state.get("running"):
        products = batch_workflow_state.get("products", [])
        current_index = batch_workflow_state.get("current_index", 0)

        if not isinstance(products, list) or not isinstance(current_index, int):
            st.error("Invalid batch workflow state")
            return

        if current_index >= len(products):
            batch_workflow_state["running"] = False
            st.rerun()
            return

        current_product = products[current_index]
        total_products = len(products)
        completed_count = current_index

        with st.status(
            f"🔄 Batch Workflow: Processing {completed_count}/{total_products} products",
            expanded=True,
        ):
            st.write(f"### Current Product: {current_product.name}")
            st.write(f"**Step:** {batch_workflow_state.get('current_step', 'Initializing...')}")

            # Progress bar
            st.progress(
                completed_count / total_products,
                text=f"Overall Progress: {completed_count}/{total_products}",
            )

            # Process current product
            if not batch_workflow_state.get("stop_requested"):
                if current_index < len(products):
                    product = products[current_index]

                    # Step 1: Crawl
                    batch_workflow_state["current_step"] = f"Crawling {product.name}..."
                    st.info(f"🔍 Crawling {product.name}...")
                    st.rerun()

                    # Initialize individual workflow state for this product
                    individual_workflow_key = f"workflow_{product.slug}"
                    if individual_workflow_key not in st.session_state:
                        st.session_state[individual_workflow_key] = {
                            "running": True,
                            "current_step": "crawling",
                            "step_progress": {
                                "crawling": {"status": "running", "message": "Starting crawl..."},
                                "summarization": {"status": "pending"},
                                "overview": {"status": "pending"},
                            },
                            "crawl_stats": None,
                        }

                    individual_state = st.session_state[individual_workflow_key]

                    # Run crawl
                    if individual_state["step_progress"]["crawling"]["status"] == "running":
                        crawl_stats = run_crawl_async(product)
                        if crawl_stats:
                            individual_state["step_progress"]["crawling"] = {
                                "status": "complete",
                                "message": f"Found {crawl_stats.legal_documents_stored} documents",
                            }
                            individual_state["crawl_stats"] = crawl_stats
                        else:
                            individual_state["step_progress"]["crawling"] = {
                                "status": "failed",
                                "message": "Crawl failed",
                            }
                        st.rerun()

                    # Step 2: Summarize
                    if individual_state["step_progress"]["crawling"]["status"] == "complete":
                        batch_workflow_state["current_step"] = (
                            f"Summarizing documents for {product.name}..."
                        )
                        st.info(f"📝 Summarizing {product.name}...")
                        individual_state["step_progress"]["summarization"] = {"status": "running"}

                        success = run_summarization_async(product.slug)
                        if success:
                            individual_state["step_progress"]["summarization"] = {
                                "status": "complete"
                            }
                        else:
                            individual_state["step_progress"]["summarization"] = {
                                "status": "failed"
                            }
                        st.rerun()

                    # Step 3: Overview
                    if individual_state["step_progress"]["summarization"]["status"] == "complete":
                        batch_workflow_state["current_step"] = (
                            f"Generating overview for {product.name}..."
                        )
                        st.info(f"📊 Generating overview for {product.name}...")
                        individual_state["step_progress"]["overview"] = {"status": "running"}

                        success = run_overview_async(product.slug)
                        if success:
                            individual_state["step_progress"]["overview"] = {"status": "complete"}
                        else:
                            individual_state["step_progress"]["overview"] = {"status": "failed"}
                        st.rerun()

                    # Check if product is complete
                    all_steps_complete = all(
                        step.get("status") in ["complete", "failed"]
                        for step in individual_state["step_progress"].values()
                    )

                    if all_steps_complete:
                        # Store result
                        results = batch_workflow_state.get("results", [])
                        if isinstance(results, list):
                            results.append(
                                {
                                    "product": product.name,
                                    "slug": product.slug,
                                    "status": "complete"
                                    if all(
                                        step.get("status") == "complete"
                                        for step in individual_state["step_progress"].values()
                                    )
                                    else "failed",
                                    "steps": individual_state["step_progress"],
                                }
                            )
                            batch_workflow_state["results"] = results

                        # Move to next product
                        batch_workflow_state["current_index"] = current_index + 1
                        del st.session_state[individual_workflow_key]
                        st.rerun()
            else:
                st.warning("Stop requested. Finishing current product...")

        # Check if batch is complete
        if current_index >= len(products):
            batch_workflow_state["running"] = False

            # Show final results
            results = batch_workflow_state.get("results", [])
            results_count = len(results) if isinstance(results, list) else 0
            st.success(f"✅ Batch workflow completed! Processed {results_count} products")

            st.write("### Results Summary")
            if isinstance(results, list):
                for result in results:
                    status_icon = "✅" if result["status"] == "complete" else "❌"
                    st.write(f"{status_icon} **{result['product']}** ({result['slug']})")
                    with st.expander(f"View details for {result['product']}"):
                        for step_name, step_info in result["steps"].items():
                            step_display = {
                                "crawling": "Crawling",
                                "summarization": "Summarization",
                                "overview": "Overview",
                            }.get(step_name, step_name)
                            status = "✅" if step_info.get("status") == "complete" else "❌"
                            st.write(
                                f"{status} {step_display}: {step_info.get('message', step_info.get('status'))}"
                            )

            # Clear batch workflow state
            batch_workflow_state["running"] = False
            batch_workflow_state["results"] = []
            batch_workflow_state["current_index"] = 0
            st.rerun()

    # Display workflow status and progress
    if workflow_state.get("running") or workflow_state.get("crawl_future"):
        # Check if crawl is still running
        if workflow_state.get("crawl_future") and not workflow_state["crawl_future"].done():
            stop_disabled = workflow_state.get("stop_requested", False)
            if st.button(
                "⏹ Stop Workflow",
                type="secondary",
                disabled=stop_disabled,
                key=f"stop_workflow_btn_{selected_product.slug}",
            ):
                if workflow_state.get("stop_event"):
                    workflow_state["stop_event"].set()
                    workflow_state["stop_requested"] = True
            if workflow_state.get("stop_requested"):
                st.info("Stop requested. Finishing current step safely...")

            # Poll for logs
            log_path = Path(workflow_state["log_path"]) if workflow_state.get("log_path") else None
            if log_path and log_path.exists():
                new_content, new_position = read_log_file_tail(
                    log_path, workflow_state["log_position"], max_lines=1000
                )
                if new_content:
                    workflow_state["log_content"] += new_content
                    all_lines = workflow_state["log_content"].splitlines(keepends=True)
                    if len(all_lines) > 1000:
                        workflow_state["log_content"] = "".join(all_lines[-1000:])
                    workflow_state["log_position"] = new_position

            # Show workflow progress
            with st.status(
                f"🔄 Running complete workflow for {selected_product.name}...",
                expanded=True,
            ):
                st.write("### Workflow Progress")

                # Step 1: Crawling
                crawl_status = workflow_state["step_progress"].get("crawling", {})
                if crawl_status.get("status") == "running":
                    st.write("1️⃣ **Crawling** - 🔄 In progress...")
                elif crawl_status.get("status") == "complete":
                    st.write("1️⃣ **Crawling** - ✅ Complete")
                elif crawl_status.get("status") == "failed":
                    st.write("1️⃣ **Crawling** - ❌ Failed")
                else:
                    st.write("1️⃣ **Crawling** - ⏳ Pending")

                # Step 2: Summarization
                summ_status = workflow_state["step_progress"].get("summarization", {})
                if summ_status.get("status") == "running":
                    st.write("2️⃣ **Summarization** - 🔄 In progress...")
                elif summ_status.get("status") == "complete":
                    st.write("2️⃣ **Summarization** - ✅ Complete")
                elif summ_status.get("status") == "failed":
                    st.write("2️⃣ **Summarization** - ❌ Failed")
                else:
                    st.write("2️⃣ **Summarization** - ⏳ Pending")

                # Step 3: Overview
                overview_status = workflow_state["step_progress"].get("overview", {})
                if overview_status.get("status") == "running":
                    st.write("3️⃣ **Overview** - 🔄 In progress...")
                elif overview_status.get("status") == "complete":
                    st.write("3️⃣ **Overview** - ✅ Complete")
                elif overview_status.get("status") == "failed":
                    st.write("3️⃣ **Overview** - ❌ Failed")
                else:
                    st.write("3️⃣ **Overview** - ⏳ Pending")

                # Display logs
                if workflow_state["log_content"]:
                    st.write("---")
                    st.subheader("📋 Workflow Logs (Live)")
                    if log_path:
                        st.caption(f"Log file: `{log_path}`")
                    st.code(workflow_state["log_content"], language="text")
                else:
                    st.info("📝 Waiting for logs to appear...")

            # Rerun to update progress
            time.sleep(0.5)
            st.rerun()

        else:
            # Crawl completed, check status and proceed to next step
            if workflow_state.get("crawl_future"):
                try:
                    workflow_state["crawl_stats"] = workflow_state["crawl_future"].result()
                    if workflow_state["crawl_stats"]:
                        workflow_state["step_progress"]["crawling"] = {
                            "status": "complete",
                            "message": f"Found {workflow_state['crawl_stats'].legal_documents_stored} documents",
                        }
                    else:
                        workflow_state["step_progress"]["crawling"] = {
                            "status": "failed",
                            "message": "Crawling failed",
                        }
                except Exception as e:
                    workflow_state["crawl_stats"] = None
                    workflow_state["step_progress"]["crawling"] = {
                        "status": "failed",
                        "message": f"Crawling error: {str(e)}",
                    }
                finally:
                    # Clean up executor
                    if "crawl_executor" in workflow_state:
                        workflow_state["crawl_executor"].shutdown(wait=False)
                        del workflow_state["crawl_executor"]
                    workflow_state["crawl_future"] = None

            # If crawl succeeded, proceed to summarization
            if (
                workflow_state["step_progress"]["crawling"]["status"] == "complete"
                and workflow_state["step_progress"]["summarization"]["status"] == "pending"
            ):
                workflow_state["current_step"] = "summarization"
                workflow_state["step_progress"]["summarization"] = {
                    "status": "running",
                    "message": "Starting document analysis...",
                }
                # Rerun to show summarization has started
                st.rerun()

            # Run summarization if it's in running state
            if workflow_state["step_progress"]["summarization"]["status"] == "running":
                # Run summarization with spinner
                with st.spinner("Analyzing documents... This may take several minutes."):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        success = run_summarization_async(selected_product.slug, loop)
                        if success:
                            workflow_state["step_progress"]["summarization"] = {
                                "status": "complete",
                                "message": "All documents analyzed",
                            }
                        else:
                            workflow_state["step_progress"]["summarization"] = {
                                "status": "failed",
                                "message": "Summarization failed",
                            }
                    finally:
                        loop.close()
                # Rerun to show summarization completed
                st.rerun()

            # If summarization succeeded, proceed to overview
            if (
                workflow_state["step_progress"]["summarization"]["status"] == "complete"
                and workflow_state["step_progress"]["overview"]["status"] == "pending"
            ):
                workflow_state["current_step"] = "overview"
                workflow_state["step_progress"]["overview"] = {
                    "status": "running",
                    "message": "Generating product overview...",
                }
                # Rerun to show overview has started
                st.rerun()

            # Run overview if it's in running state
            if workflow_state["step_progress"]["overview"]["status"] == "running":
                # Run overview generation with spinner
                with st.spinner("Generating product overview... This may take a few minutes."):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        success = run_overview_async(selected_product.slug, loop)
                        if success:
                            workflow_state["step_progress"]["overview"] = {
                                "status": "complete",
                                "message": "Overview generated successfully",
                            }
                        else:
                            workflow_state["step_progress"]["overview"] = {
                                "status": "failed",
                                "message": "Overview generation failed",
                            }
                    finally:
                        loop.close()
                # Rerun to show overview completed
                st.rerun()

            # Show final status
            all_complete = all(
                step.get("status") == "complete"
                for step in workflow_state["step_progress"].values()
            )
            any_failed = any(
                step.get("status") == "failed" for step in workflow_state["step_progress"].values()
            )

            if all_complete:
                status_label = f"✅ Complete workflow for {selected_product.name} finished!"
                status_state = "complete"
            elif any_failed:
                status_label = f"❌ Workflow for {selected_product.name} encountered errors"
                status_state = "error"
            else:
                status_label = f"🔄 Workflow for {selected_product.name} in progress..."
                status_state = "running"

            with st.status(status_label, expanded=False, state=status_state):
                st.write("### Final Status")

                for step_name, step_info in workflow_state["step_progress"].items():
                    step_display = {
                        "crawling": "1. Crawling",
                        "summarization": "2. Summarization",
                        "overview": "3. Overview",
                    }.get(step_name, step_name)

                    if step_info.get("status") == "complete":
                        st.success(f"{step_display} - ✅ {step_info.get('message', 'Complete')}")
                    elif step_info.get("status") == "failed":
                        st.error(f"{step_display} - ❌ {step_info.get('message', 'Failed')}")
                    else:
                        st.info(f"{step_display} - ⏳ {step_info.get('message', 'Pending')}")

                # Show crawl stats if available
                if workflow_state.get("crawl_stats"):
                    st.write("---")
                    st.write("### Crawl Results")
                    st.write(
                        f"**Documents found:** {workflow_state['crawl_stats'].legal_documents_stored}"
                    )

            if all_complete:
                st.success("🎉 Complete workflow finished successfully!")
                st.info("""
                **What was accomplished:**
                • Legal documents were discovered and stored
                • All documents were analyzed for privacy practices
                • A comprehensive product overview was generated
                • You can now view the overview in the "Deep Analysis & Overview" page
                """)
            elif any_failed:
                st.error("Some steps failed. Please check the logs and try again.")

            # Clear workflow state after showing results
            if workflow_key in st.session_state:
                del st.session_state[workflow_key]

    # Back to products button
    st.write("---")
    if st.button("← Back to Products", key="back_to_products_from_workflow"):
        # Clear workflow session state and navigate back
        if "selected_product_for_workflow" in st.session_state:
            del st.session_state["selected_product_for_workflow"]
        st.session_state["current_page"] = "view_products"
        st.rerun()
