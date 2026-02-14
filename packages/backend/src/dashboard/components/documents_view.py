from datetime import datetime

import streamlit as st

from src.dashboard.components.summarization import run_summarization_async
from src.dashboard.db_utils import get_all_products_isolated, get_product_documents_by_id_isolated
from src.dashboard.utils import run_async_with_retry
from src.models.product import Product


def format_datetime(dt: datetime | None) -> str:
    """Format datetime for display."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_effective_date(dt: datetime | None) -> str:
    """Format effective date for display."""
    if dt is None:
        return "Not specified"
    return dt.strftime("%Y-%m-%d")


def show_documents_view() -> None:
    st.title("📄 Product Documents")

    # Get all products
    products = run_async_with_retry(get_all_products_isolated())

    if products is None:
        st.error(
            "Failed to load products from database. Please check your connection and try again."
        )
        return

    if not products:
        st.warning("No products found. Please create a product first.")
        return

    # Check if a product was preselected (from session state)
    preselected_product_id = st.session_state.get("selected_product_for_documents", None)

    # Create product dropdown options
    product_options = {f"{product.name} ({product.slug})": product for product in products}
    default_index = 0

    if preselected_product_id:
        # Find the index of the preselected product
        for idx, product in enumerate(products):
            if product.id == preselected_product_id:
                default_index = idx
                break

    # Product selection dropdown
    selected_product_name = st.selectbox(
        "Select Product",
        options=list(product_options.keys()),
        index=default_index,
        key="documents_product_select",
    )

    selected_product: Product = product_options[selected_product_name]

    # Load documents for selected product
    with st.spinner(f"Loading documents for {selected_product.name}..."):
        documents = run_async_with_retry(get_product_documents_by_id_isolated(selected_product.id))

    if documents is None:
        st.error("Failed to load documents from database.")
        return

    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Documents", len(documents))

    with col2:
        analyzed_count = sum(1 for doc in documents if doc.analysis is not None)
        st.metric("Analyzed Documents", analyzed_count)

    with col3:
        pending_count = len(documents) - analyzed_count
        st.metric("Pending Analysis", pending_count)

    with col4:
        # Count documents by type
        doc_types = {}
        for doc in documents:
            doc_type = doc.doc_type
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
        unique_types = len(doc_types)
        st.metric("Document Types", unique_types)

    st.divider()

    # Document Summarization Section
    st.subheader("🔍 Document Analysis")

    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        if st.button(
            "🚀 Summarize Documents", type="primary", key="summarize_documents_from_docs_page"
        ):
            if not documents:
                st.warning("No documents to analyze.")
            else:
                # Start document analysis
                with st.spinner(
                    f"Analyzing documents for {selected_product.name}... This may take several minutes."
                ):
                    progress_placeholder = st.empty()
                    progress_placeholder.info("🔍 Processing documents...")

                    # Run the summarization process
                    success = run_summarization_async(selected_product.slug)

                    progress_placeholder.empty()

                    if success:
                        st.success("✅ Document analysis completed successfully!")
                        st.info("""
                        **What happened:**
                        • Each document was analyzed for privacy practices
                        • Summaries were generated with transparency and data usage scores
                        • Key points were extracted for each document
                        • Analysis data was stored in the database
                        """)
                        # Refresh the page to show updated analysis count
                        st.rerun()
                    else:
                        st.error("Document analysis failed. Please check the logs and try again.")

    st.divider()

    # Search and filter
    col1, col2 = st.columns(2)

    with col1:
        search_term = st.text_input(
            "Search documents", placeholder="Search by URL, title, or type..."
        )

    with col2:
        doc_type_filter = st.selectbox(
            "Filter by Type",
            options=["All"] + sorted({doc.doc_type for doc in documents}),
            key="doc_type_filter",
        )

    # Filter documents
    filtered_documents = documents
    if search_term:
        search_lower = search_term.lower()
        filtered_documents = [
            doc
            for doc in filtered_documents
            if search_lower in doc.url.lower()
            or (doc.title and search_lower in doc.title.lower())
            or search_lower in doc.doc_type.lower()
        ]

    if doc_type_filter != "All":
        filtered_documents = [doc for doc in filtered_documents if doc.doc_type == doc_type_filter]

    # Sort documents by created_at (newest first)
    filtered_documents.sort(key=lambda x: x.created_at, reverse=True)

    if not filtered_documents:
        st.info("No documents found matching your criteria.")
        return

    st.write(f"**Showing {len(filtered_documents)} of {len(documents)} documents**")

    # Display documents
    for document in filtered_documents:
        with st.expander(
            f"📄 {document.title or document.url} ({document.doc_type})",
            expanded=False,
        ):
            # Document metadata in columns
            meta_col1, meta_col2 = st.columns(2)

            with meta_col1:
                st.write("**Basic Information:**")
                st.write(f"• **ID:** `{document.id}`")
                st.write(f"• **Type:** {document.doc_type}")
                st.write(f"• **URL:** [{document.url}]({document.url})")
                st.write(f"• **Title:** {document.title or 'N/A'}")

            with meta_col2:
                st.write("**Dates & Metadata:**")
                st.write(f"• **Created:** {format_datetime(document.created_at)}")
                st.write(f"• **Effective Date:** {format_effective_date(document.effective_date)}")
                st.write(f"• **Locale:** {document.locale or 'N/A'}")
                st.write(
                    f"• **Regions:** {', '.join(str(r) for r in document.regions) if document.regions else 'N/A'}"
                )

            # Analysis status
            st.divider()
            if document.analysis:
                st.success("✅ **Document Analyzed**")
                analysis_col1, analysis_col2 = st.columns(2)

                with analysis_col1:
                    st.write("**Analysis Summary:**")
                    st.write(
                        document.analysis.summary[:500] + "..."
                        if len(document.analysis.summary) > 500
                        else document.analysis.summary
                    )

                    st.write("**Risk Assessment:**")
                    st.write(f"• **Risk Score:** {document.analysis.risk_score}/10")
                    st.write(f"• **Verdict:** {document.analysis.verdict}")

                with analysis_col2:
                    st.write("**Scores:**")
                    for score_name, score_data in document.analysis.scores.items():
                        # score_data is a DocumentAnalysisScores object
                        if hasattr(score_data, "score"):
                            score = score_data.score
                            st.write(f"• **{score_name.replace('_', ' ').title()}:** {score}/10")
                        elif isinstance(score_data, dict):
                            # Fallback for dict format
                            score = score_data.get("score", "N/A")
                            st.write(f"• **{score_name.replace('_', ' ').title()}:** {score}/10")

                    if document.analysis.liability_risk is not None:
                        st.write(f"• **Liability Risk:** {document.analysis.liability_risk}/10")

                    if document.analysis.compliance_status:
                        st.write("**Compliance Status:**")
                        for reg, score in document.analysis.compliance_status.items():
                            st.write(f"• **{reg}:** {score}/10")

                if document.analysis.keypoints:
                    st.write("**Key Points:**")
                    for point in document.analysis.keypoints[:5]:  # Show first 5
                        st.write(f"• {point}")
            else:
                st.warning("⚠️ **Document Not Analyzed** - Analysis pending")

            # Additional metadata
            if document.metadata:
                st.divider()
                with st.expander("View Full Metadata"):
                    st.json(document.metadata)

            # Versions
            if document.versions:
                st.divider()
                st.write(f"**Document Versions:** {len(document.versions)}")
                with st.expander("View Versions"):
                    for version_idx, version in enumerate(document.versions):
                        st.write(f"**Version {version_idx + 1}:**")
                        st.json(version)

    # Back button
    st.divider()
    if st.button("← Back to Products", key="back_to_products_from_documents"):
        # Clear session state and navigate back
        if "selected_product_for_documents" in st.session_state:
            del st.session_state["selected_product_for_documents"]
        st.session_state["current_page"] = "view_products"
        st.rerun()
