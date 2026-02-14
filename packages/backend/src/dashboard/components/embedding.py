import streamlit as st

from src.dashboard.dashboard_embedding import embed_product, embed_products
from src.dashboard.db_utils import get_all_products_isolated
from src.dashboard.utils import run_async


def show_embedding() -> None:
    st.title("🔍 Generate & Store Embeddings")

    # Get all products
    products = run_async(get_all_products_isolated())

    if products is None:
        st.error("Failed to load products from database")
        return

    if not products:
        st.warning("No products found. Please create a product first.")
        return

    # Create product dropdown options
    product_options = {f"{product.name} ({product.slug})": product for product in products}

    # Check if a product was preselected (from session state)
    preselected_product = st.session_state.get("selected_product_for_embedding", None)
    default_index = 0

    if preselected_product:
        # Find the index of the preselected product
        for i, product in enumerate(products):
            if product.id == preselected_product:
                default_index = i
                break

    selected_product_key = st.selectbox(
        "Select Product for Embedding",
        options=list(product_options.keys()),
        index=default_index,
        help="Choose which product's documents you want to embed for semantic search",
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

    # Embedding section
    st.write("---")
    st.subheader("Generate Document Embeddings")

    st.info(f"""
    **This will:**
    • Process all documents for {selected_product.name}
    • Split documents into chunks for better search
    • Generate vector embeddings using Mistral's embedding model
    • Store embeddings in Pinecone for semantic search
    • This process may take several minutes depending on document count
    """)

    # Start embedding buttons
    col1, col2, col3 = st.columns([2, 1, 2])

    with col2:
        if st.button("🚀 Start Embedding", type="primary", key="start_embedding_btn"):
            # Clear any previous embedding session state
            if "selected_product_for_embedding" in st.session_state:
                del st.session_state["selected_product_for_embedding"]

            # Start embedding
            with st.spinner(
                f"Processing documents for {selected_product.name}... This may take several minutes."
            ):
                # Show progress info
                progress_placeholder = st.empty()
                progress_placeholder.info("🔍 Loading documents...")

                # Run the embedding process
                success = embed_product(selected_product.slug)

                progress_placeholder.empty()

                if success is not False:  # None or True means success
                    st.success("✅ Document embedding completed successfully!")
                    st.info(f"""
                    **What happened:**
                    • Documents were split into searchable chunks
                    • Vector embeddings were generated for each chunk
                    • Embeddings were stored in Pinecone index under namespace: `{selected_product.slug}`
                    • You can now perform semantic search on {selected_product.name}'s documents
                    """)
                else:
                    st.error("Embedding failed. Please check the logs and try again.")
                    st.info("**Common issues:**")
                    st.write("• No documents found for this product")
                    st.write("• API key issues (LLM or Pinecone)")
                    st.write("• Network connectivity problems")

    # Add Embed All button
    with col2:
        if st.button("🚀 Embed All Products", type="secondary", key="embed_all_btn"):
            # Start embedding for all products
            with st.spinner(
                "Processing documents for all products... This may take several minutes."
            ):
                # Show progress info
                progress_placeholder = st.empty()
                progress_placeholder.info("🔍 Loading documents for all products...")

                # Get all product slugs
                product_slugs = [product.slug for product in products]

                # Run the embedding process for all products
                results = embed_products(product_slugs, max_concurrency=3)

                progress_placeholder.empty()

                if results:
                    success_count = sum(1 for _, success in results if success is not False)
                    st.success(
                        f"✅ Document embedding completed for {success_count} out of {len(products)} products!"
                    )

                    # Show detailed results
                    st.info("**Embedding Results:**")
                    for slug, success in results:
                        product_name = next((p.name for p in products if p.slug == slug), slug)
                        if success is not False:
                            st.write(f"✅ {product_name}: Success")
                        else:
                            st.write(f"❌ {product_name}: Failed")

                    # Show summary
                    if success_count == len(products):
                        st.success("🎉 All products processed successfully!")
                    elif success_count > 0:
                        st.warning(
                            f"⚠️ {len(products) - success_count} products failed to process. Check the results above for details."
                        )
                    else:
                        st.error(
                            "❌ All products failed to process. Please check the logs and try again."
                        )
                else:
                    st.error(
                        "Embedding failed for all products. Please check the logs and try again."
                    )
                    st.info("**Common issues:**")
                    st.write("• No documents found for products")
                    st.write("• API key issues (LLM or Pinecone)")
                    st.write("• Network connectivity problems")

    # Back to products button
    st.write("---")
    if st.button("← Back to Products", key="back_to_products_from_embedding"):
        # Clear embedding session state and navigate back
        if "selected_product_for_embedding" in st.session_state:
            del st.session_state["selected_product_for_embedding"]
        st.session_state["current_page"] = "view_products"
        st.rerun()
