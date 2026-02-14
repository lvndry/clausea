import streamlit as st
from streamlit_tags import st_tags

from src.dashboard.db_utils import (
    delete_product_isolated,
    get_all_products_isolated,
    get_document_counts_by_product,
    update_product_isolated,
)
from src.dashboard.utils import run_async_with_retry
from src.models.product import Product
from src.models.user import UserTier


def show_edit_form(product: Product) -> None:
    """Show edit form for a product"""
    st.subheader(f"Edit Product: {product.name}")

    with st.form(f"edit_product_form_{product.id}"):
        # Pre-fill form with existing data
        name = st.text_input("Product Name", value=product.name)
        slug = st.text_input("Product Slug", value=product.slug)

        # Use tag inputs instead of text areas
        domains = st_tags(
            label="Domains",
            text="Press enter to add a domain",
            value=product.domains if product.domains else [],
            key=f"domains_{product.id}",
        )
        categories = st_tags(
            label="Categories",
            text="Press enter to add a category",
            value=product.categories if product.categories else [],
            key=f"categories_{product.id}",
        )
        crawl_base_urls = st_tags(
            label="Crawl Base URLs",
            text="Press enter to add a URL",
            value=product.crawl_base_urls if product.crawl_base_urls else [],
            key=f"crawl_urls_{product.id}",
        )

        # Tier visibility section
        st.write("**Tier Visibility:**")
        st.write("Select which user tiers can access this product:")

        # Get current tier visibility
        current_tiers = (
            product.visible_to_tiers
            if hasattr(product, "visible_to_tiers")
            else [UserTier.FREE, UserTier.BUSINESS, UserTier.ENTERPRISE]
        )

        free_tier = st.checkbox(
            "Free Tier", value=UserTier.FREE in current_tiers, key=f"free_tier_{product.id}"
        )
        business_tier = st.checkbox(
            "Business Tier",
            value=UserTier.BUSINESS in current_tiers,
            key=f"business_tier_{product.id}",
        )
        enterprise_tier = st.checkbox(
            "Enterprise Tier",
            value=UserTier.ENTERPRISE in current_tiers,
            key=f"enterprise_tier_{product.id}",
        )

        # Validate that at least one tier is selected
        if not any([free_tier, business_tier, enterprise_tier]):
            st.error("At least one tier must be selected!")
            return

        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Update Product", type="primary")
        with col2:
            cancelled = st.form_submit_button("Cancel")

        if cancelled:
            # Clear the edit state
            if f"editing_product_{product.id}" in st.session_state:
                del st.session_state[f"editing_product_{product.id}"]
            st.rerun()

        if submitted:
            try:
                # Tags already return lists, just need to filter empty strings
                domains_list = [domain.strip() for domain in domains if domain.strip()]
                categories_list = [category.strip() for category in categories if category.strip()]
                crawl_base_urls_list = (
                    [url.strip() for url in crawl_base_urls if url.strip()]
                    if crawl_base_urls
                    else None
                )

                # Build tier visibility list
                visible_tiers = []
                if free_tier:
                    visible_tiers.append(UserTier.FREE)
                if business_tier:
                    visible_tiers.append(UserTier.BUSINESS)
                if enterprise_tier:
                    visible_tiers.append(UserTier.ENTERPRISE)

                # Create updated product instance
                updated_product = Product(
                    id=product.id,  # Keep the same ID
                    name=name,
                    slug=slug,
                    domains=domains_list,
                    categories=categories_list,
                    crawl_base_urls=crawl_base_urls_list if crawl_base_urls_list else [],
                    visible_to_tiers=visible_tiers,
                )

                # Update in database with retry
                success = run_async_with_retry(update_product_isolated(updated_product))

                if success:
                    st.success(f"Product '{name}' updated successfully!")
                    # Clear the edit state
                    if f"editing_product_{product.id}" in st.session_state:
                        del st.session_state[f"editing_product_{product.id}"]
                    st.rerun()
                else:
                    st.error("Failed to update product. Please try again.")

            except Exception as e:
                st.error(f"Error updating product: {str(e)}")


def show_delete_confirmation(product: Product) -> None:
    """Show delete confirmation dialog"""
    st.error(f"⚠️ **Delete Product: {product.name}**")
    st.write("**This action cannot be undone!**")
    st.write("All data associated with this product will be permanently deleted, including:")
    st.write("• Product information")
    st.write("• Associated documents")
    st.write("• Crawl data")

    st.write("---")

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("🗑️ **DELETE**", key=f"confirm_delete_{product.id}", type="primary"):
            # Perform the deletion with retry
            success = run_async_with_retry(delete_product_isolated(product.id))

            if success:
                st.success(f"Product '{product.name}' has been deleted successfully!")
                # Clear all related session state
                delete_confirm_key = f"delete_confirm_{product.id}"
                if delete_confirm_key in st.session_state:
                    del st.session_state[delete_confirm_key]
                st.rerun()
            else:
                st.error("Failed to delete product. Please try again.")

    with col2:
        if st.button("Cancel", key=f"cancel_delete_{product.id}"):
            # Clear the delete confirmation state
            delete_confirm_key = f"delete_confirm_{product.id}"
            if delete_confirm_key in st.session_state:
                del st.session_state[delete_confirm_key]
            st.rerun()


def show_product_view() -> None:
    st.title("All Products")

    # Add a refresh button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Refresh", type="secondary"):
            st.rerun()

    try:
        with st.spinner("Loading products..."):
            products = run_async_with_retry(get_all_products_isolated())
            document_counts = run_async_with_retry(get_document_counts_by_product()) or {}

        if products is None:
            st.error(
                "Failed to load products from database. Please check your connection and try again."
            )
            st.info("💡 **Troubleshooting tips:**")
            st.write("• Make sure your MongoDB connection is working")
            st.write("• Check that the MONGO_URI environment variable is set correctly")
            st.write("• Try refreshing the page")
            return

        if not products:
            st.info("No products found. Create your first product!")
            return

        st.success(f"✅ Loaded {len(products)} products successfully")

        # Create search/filter functionality
        search_term = st.text_input("Search products", placeholder="Enter product name or slug...")

        # Filter products based on search term
        if search_term:
            filtered_products = [
                product
                for product in products
                if search_term.lower() in product.name.lower()
                or search_term.lower() in product.slug.lower()
                or any(search_term.lower() in domain.lower() for domain in product.domains)
                or any(search_term.lower() in category.lower() for category in product.categories)
            ]
        else:
            filtered_products = products

        # Sort filtered products by name (case-insensitive)
        filtered_products = sorted(filtered_products, key=lambda x: x.name.lower())

        if not filtered_products:
            st.warning(f"No products found matching '{search_term}'")
            return

        # Display products in a grid/card layout
        for _i, product in enumerate(filtered_products):
            # Check if this product is being edited or deleted
            edit_key = f"editing_product_{product.id}"
            delete_confirm_key = f"delete_confirm_{product.id}"
            is_editing = st.session_state.get(edit_key, False)
            is_confirming_delete = st.session_state.get(delete_confirm_key, False)

            if is_confirming_delete:
                # Show delete confirmation dialog
                show_delete_confirmation(product)
            elif is_editing:
                # Show edit form instead of product card
                show_edit_form(product)
            else:
                # Show normal product card
                with st.expander(f"🏢 {product.name} ({product.slug})", expanded=False):
                    # Key metric at the top
                    doc_count = document_counts.get(product.id, 0)
                    metric_col1, metric_col2, metric_col3 = st.columns(3)
                    with metric_col1:
                        st.metric("Documents", doc_count)

                    # Basic product information
                    st.write("**Product Information:**")
                    info_col1, info_col2, info_col3 = st.columns(3)
                    with info_col1:
                        st.write(f"**ID:** `{product.id}`")
                    with info_col2:
                        st.write(f"**Name:** {product.name}")
                    with info_col3:
                        st.write(f"**Slug:** {product.slug}")

                    st.divider()

                    # Lists section - organized in columns
                    lists_col1, lists_col2, lists_col3 = st.columns(3)

                    with lists_col1:
                        st.write("**Domains:**")
                        if product.domains:
                            for domain in product.domains:
                                st.write(f"• {domain}")
                        else:
                            st.write("*No domains configured*")

                    with lists_col2:
                        st.write("**Categories:**")
                        if product.categories:
                            for category in product.categories:
                                st.write(f"• {category}")
                        else:
                            st.write("*No categories*")

                    with lists_col3:
                        st.write("**Crawl Base URLs:**")
                        if product.crawl_base_urls:
                            for url in product.crawl_base_urls:
                                st.write(f"• [{url}]({url})")
                        else:
                            st.write("*None configured*")

                    st.divider()

                    # Tier visibility section
                    st.write("**Tier Visibility:**")
                    if hasattr(product, "visible_to_tiers") and product.visible_to_tiers:
                        tier_labels = []
                        for tier in product.visible_to_tiers:
                            if tier == UserTier.FREE:
                                tier_labels.append("🟢 Free")
                            elif tier == UserTier.BUSINESS:
                                tier_labels.append("🔵 Business")
                            elif tier == UserTier.ENTERPRISE:
                                tier_labels.append("🟣 Enterprise")

                        if len(tier_labels) == 3:
                            st.success("✅ Accessible to all tiers")
                        elif len(tier_labels) == 1:
                            st.warning(f"⚠️ Premium content: {tier_labels[0]}")
                        else:
                            st.info(f"📊 Limited access: {', '.join(tier_labels)}")
                    else:
                        st.info("📊 Accessible to all tiers (default)")

                    # Action buttons
                    st.write("---")
                    col3, col4, col5, col6, col7 = st.columns(5)
                    with col3:
                        if st.button("📊 Analytics", key=f"analytics_{product.id}"):
                            st.info("Analytics feature coming soon!")
                    with col4:
                        if st.button("📄 Documents", key=f"docs_{product.id}"):
                            # Set the selected product for documents and navigate to documents page
                            st.session_state["selected_product_for_documents"] = product.id
                            st.session_state["current_page"] = "view_documents"
                            st.rerun()
                    with col5:
                        if st.button("🕷️ Crawl", key=f"crawl_{product.id}"):
                            st.session_state["selected_product_for_crawl"] = product.id
                            st.session_state["current_page"] = "start_crawling"
                            st.rerun()
                    with col6:
                        if st.button("✏️ Edit", key=f"edit_{product.id}"):
                            st.session_state[edit_key] = True
                            st.rerun()
                    with col7:
                        if st.button("🗑️ Delete", key=f"delete_{product.id}"):
                            st.session_state[delete_confirm_key] = True
                            st.rerun()

        # Summary statistics
        st.write("---")
        st.subheader("Summary Statistics")

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("Total Products", len(products))

        with col2:
            total_domains = sum(len(product.domains) for product in products)
            st.metric("Total Domains", total_domains)

        with col3:
            total_documents = sum(document_counts.get(product.id, 0) for product in products)
            st.metric("Total Documents", total_documents)

        with col4:
            products_with_crawl_urls = len([p for p in products if p.crawl_base_urls])
            st.metric("Products with Crawl URLs", products_with_crawl_urls)

        with col5:
            unique_categories: set[str] = set()
            for product in products:
                unique_categories.update(product.categories)
            st.metric("Unique Categories", len(unique_categories))

        # Tier visibility statistics
        st.write("---")
        st.subheader("Tier Visibility Statistics")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            # Count products accessible to each tier
            free_accessible = len(
                [
                    p
                    for p in products
                    if hasattr(p, "visible_to_tiers") and UserTier.FREE in p.visible_to_tiers
                ]
            )
            st.metric("Free Tier Accessible", free_accessible)

        with col2:
            business_accessible = len(
                [
                    p
                    for p in products
                    if hasattr(p, "visible_to_tiers") and UserTier.BUSINESS in p.visible_to_tiers
                ]
            )
            st.metric("Business Tier Accessible", business_accessible)

        with col3:
            enterprise_accessible = len(
                [
                    p
                    for p in products
                    if hasattr(p, "visible_to_tiers") and UserTier.ENTERPRISE in p.visible_to_tiers
                ]
            )
            st.metric("Enterprise Tier Accessible", enterprise_accessible)

        with col4:
            # Count premium-only products (business+ only)
            premium_only = len(
                [
                    p
                    for p in products
                    if hasattr(p, "visible_to_tiers") and UserTier.FREE not in p.visible_to_tiers
                ]
            )
            st.metric("Premium Only", premium_only)

        # Products without crawl URLs
        products_without_crawl_urls = [p for p in products if not p.crawl_base_urls]

        if products_without_crawl_urls:
            st.write("---")
            st.write("**⚠️ Products without Crawl Base URLs:**")
            product_names = [product.name for product in products_without_crawl_urls]
            st.write(", ".join(product_names))

            if len(products_without_crawl_urls) == 1:
                st.info("1 product needs crawl URLs configured.")
            else:
                st.info(f"{len(products_without_crawl_urls)} products need crawl URLs configured.")
    except Exception as e:
        st.error(f"Error loading products: {str(e)}")
        st.write("Please try refreshing the page or check your database connection.")
        st.info("💡 **Troubleshooting tips:**")
        st.write("• Check that your MongoDB connection is working")
        st.write("• Verify your environment variables are set correctly")
        st.write("• Try restarting the Streamlit application")
