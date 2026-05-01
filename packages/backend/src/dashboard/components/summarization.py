import asyncio
from collections.abc import AsyncGenerator

import streamlit as st

from src.analyser import analyse_product_documents, generate_product_overview
from src.dashboard.db_utils import (
    get_all_products_isolated,
    get_dashboard_db,
    get_product_documents_isolated,
)
from src.dashboard.utils import run_async
from src.services.service_factory import create_document_service, create_product_service


async def run_analysis_async_internal(
    product_slug: str,
) -> bool:
    """Run document analysis in an isolated async context"""
    try:
        db = await get_dashboard_db()
        try:
            document_svc = create_document_service()
            await analyse_product_documents(db.db, product_slug, document_svc)
            return True
        finally:
            await db.disconnect()
    except Exception as e:
        st.error(f"Analysis error: {str(e)}")
        return False


def run_analysis_async(product_slug: str, loop: asyncio.AbstractEventLoop | None = None) -> bool:
    """Run document analysis in an isolated async context"""
    try:
        should_close_loop = False
        if loop is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            should_close_loop = True

        try:
            loop.run_until_complete(run_analysis_async_internal(product_slug))
            return True
        finally:
            if should_close_loop:
                # Clean up pending tasks
                pending_tasks = asyncio.all_tasks(loop)
                if pending_tasks:
                    # Cancel all tasks at once and wait for completion
                    for task in pending_tasks:
                        task.cancel()

                    # Wait for all cancelled tasks to finish
                    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))

                loop.close()
    except Exception as e:
        st.error(f"Analysis error: {str(e)}")
        return False


async def generate_overview_async(product_slug: str) -> AsyncGenerator[str, None]:
    """Generate product overview for a product"""
    db = await get_dashboard_db()
    product_svc = create_product_service()
    document_svc = create_document_service()
    result = await generate_product_overview(
        db.db, product_slug, product_svc=product_svc, document_svc=document_svc
    )
    summary_content = str(result)  # or format as needed
    yield summary_content


def show_analysis() -> None:
    st.title("📋 Document Analysis")

    # Get all products
    products = run_async(get_all_products_isolated())

    if products is None:
        st.error("Failed to load products from database")
        return

    if not products:
        st.warning("No products found. Please create a product first.")
        return

    # Add Summarize All section
    st.write("---")
    st.subheader("🌐 Analyse All Products")

    st.info("""
    **This will:**
    • Analyze documents for all products
    • Generate privacy-focused summaries for each document
    • Extract key points and transparency scores
    • This process may take several minutes depending on the number of products and documents
    """)

    if st.button("🚀 Analyse All Products", type="primary", key="summarize_all_btn"):
        with st.spinner("Analyzing documents for all products... This may take several minutes."):
            progress_placeholder = st.empty()
            progress_placeholder.info("🔍 Processing documents...")

            # Create a single loop for all products
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                all_success = True
                for product in products:
                    progress_placeholder.info(f"Processing {product.name}...")
                    success = run_analysis_async(product.slug, loop)
                    if not success:
                        all_success = False
                        st.error(f"Failed to process documents for {product.name}")
            finally:
                # Clean up the loop after all products are processed
                pending_tasks = asyncio.all_tasks(loop)
                if pending_tasks:
                    for task in pending_tasks:
                        task.cancel()
                    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                loop.close()

            progress_placeholder.empty()

            if all_success:
                st.success("✅ Document analysis completed successfully for all products!")
                st.info("""
                **What happened:**
                • All documents were analyzed for privacy practices
                • Summaries were generated with transparency and data usage scores
                • Key points were extracted for each document
                • Analysis data was stored in the database
                • You can now generate meta-summaries for individual products
                """)
                st.rerun()
            else:
                st.error(
                    "Document analysis failed for some products. Please check the logs and try again."
                )

    # Create product dropdown options
    product_options = {f"{product.name} ({product.slug})": product for product in products}

    # Check if a product was preselected (from session state)
    preselected_product = st.session_state.get("selected_product_for_analysis", None)
    default_index = 0

    if preselected_product:
        # Find the index of the preselected product
        for i, product in enumerate(products):
            if product.id == preselected_product:
                default_index = i
                break

    selected_product_key = st.selectbox(
        "Select Product for Analysis",
        options=list(product_options.keys()),
        index=default_index,
        help="Choose which product's documents you want to analyse",
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
        st.write("**Categories:**")
        if selected_product.categories:
            for category in selected_product.categories:
                st.write(f"• {category}")
        else:
            st.write("• No categories")

    # Get documents for this product
    st.write("---")
    documents = run_async(get_product_documents_isolated(selected_product.slug))

    if not documents:
        st.warning(f"No documents found for {selected_product.name}. Please crawl documents first.")
        return

    # Show document summary
    st.subheader("📄 Available Documents")

    # Count documents by type
    doc_type_counts: dict[str, int] = {}
    analyzed_count = 0

    for doc in documents:
        doc_type = str(doc.doc_type)
        doc_type_counts[str(doc_type)] = doc_type_counts.get(str(doc_type), 0) + 1
        if hasattr(doc, "analysis") and doc.analysis:
            analyzed_count += 1

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Documents", len(documents))
    with col2:
        st.metric("Already Analyzed", analyzed_count)
    with col3:
        st.metric("Pending Analysis", len(documents) - analyzed_count)

    # Show document types
    if doc_type_counts:
        st.write("**Document Types:**")
        for doc_type, count in doc_type_counts.items():
            st.write(f"• {doc_type.replace('_', ' ').title()}: {count}")

    # Document Analysis Section
    st.write("---")
    st.subheader("🔍 Individual Document Analysis")

    st.info(f"""
    **This will:**
    • Analyze each document for {selected_product.name}
    • Generate privacy-focused summaries for each document
    • Extract key points and transparency scores
    • Identify data usage patterns and user rights
    • This process may take several minutes depending on document count
    """)

    col1, col2, col3 = st.columns([2, 1, 2])

    with col2:
        if st.button("🚀 Analyse Documents", type="primary", key="summarize_documents_btn"):
            # Clear any previous session state
            if "selected_product_for_analysis" in st.session_state:
                del st.session_state["selected_product_for_analysis"]

            # Start document analysis
            with st.spinner(
                f"Analyzing documents for {selected_product.name}... This may take several minutes."
            ):
                progress_placeholder = st.empty()
                progress_placeholder.info("🔍 Processing documents...")

                # Run the analysis process
                success = run_analysis_async(selected_product.slug)

                progress_placeholder.empty()

                if success:
                    st.success("✅ Document analysis completed successfully!")
                    st.info("""
                    **What happened:**
                    • Each document was analyzed for privacy practices
                    • Summaries were generated with transparency and data usage scores
                    • Key points were extracted for each document
                    • Analysis data was stored in the database
                    • You can now generate a meta-summary of all documents
                    """)
                    # Refresh the page to show updated analysis count
                    st.rerun()
                else:
                    st.error("Document analysis failed. Please check the logs and try again.")

    # Meta Summary Section
    st.write("---")
    st.subheader("📊 Meta Summary")

    if analyzed_count == 0:
        st.warning("No analyzed documents found. Please run document analysis first.")
    else:
        st.info(f"""
        **Meta Summary will:**
        • Synthesize insights from all {analyzed_count} analyzed documents
        • Identify patterns and contradictions across documents
        • Provide an overall privacy assessment for {selected_product.name}
        • Highlight the most important privacy considerations for users
        """)

        if st.button("📋 Generate Overview", type="primary", key="generate_overview_btn"):
            with st.spinner(f"Generating overview for {selected_product.name}..."):
                try:
                    # Create a placeholder for streaming content
                    summary_placeholder = st.empty()

                    # Generate the meta summary using async generator
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    try:

                        async def get_summary() -> str:
                            db = await get_dashboard_db()
                            try:
                                product_svc = create_product_service()
                                document_svc = create_document_service()
                                result = await generate_product_overview(
                                    db.db,
                                    selected_product.slug,
                                    product_svc=product_svc,
                                    document_svc=document_svc,
                                )
                                return str(result)
                            finally:
                                await db.disconnect()

                        summary_content = loop.run_until_complete(get_summary())
                        summary_placeholder.markdown(summary_content)
                    finally:
                        loop.close()

                    st.success("✅ Meta summary generated successfully!")

                except Exception as e:
                    st.error(f"Failed to generate meta summary: {str(e)}")

    # Back to products button
    st.write("---")
    if st.button("← Back to Products", key="back_to_products_from_summarization"):
        # Clear summarization session state and navigate back
        if "selected_product_for_analysis" in st.session_state:
            del st.session_state["selected_product_for_analysis"]
        st.session_state["current_page"] = "view_products"
        st.rerun()
