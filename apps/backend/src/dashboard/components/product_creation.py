import shortuuid
import streamlit as st
from streamlit_tags import st_tags

from src.dashboard.db_utils import create_product_isolated, get_product_by_slug_isolated
from src.dashboard.utils import run_async_with_retry
from src.models.product import Product

# Session state keys for form fields
FORM_FIELD_KEYS = [
    "product_name_input",
    "company_name_input",
    "product_slug_input",
    "domains_input",
    "categories_input",
    "crawl_urls_input",
]

# Session state keys for success message
SUCCESS_KEYS = [
    "product_created",
    "product_created_name",
    "product_created_id",
    "product_created_slug",
]


def _clear_form_fields() -> None:
    """Clear all product form inputs from session state.

    This must be called BEFORE widgets are created, otherwise Streamlit will raise an error
    about modifying session state after widget instantiation.

    We delete the keys entirely so Streamlit widgets will use their default/placeholder values.
    """
    current_counter = st.session_state.get("form_counter", 0)
    for base_key in FORM_FIELD_KEYS:
        # Clear the current counter version
        key = f"{base_key}_{current_counter}"
        if key in st.session_state:
            del st.session_state[key]
        # Also clear the previous counter version to avoid stale data
        prev_key = f"{base_key}_{current_counter - 1}"
        if prev_key in st.session_state:
            del st.session_state[prev_key]


def _clear_success_state() -> None:
    """Clear success message state from session state."""
    for key in SUCCESS_KEYS:
        if key in st.session_state:
            del st.session_state[key]


def _render_tags(key: str, label: str, suggestions: list[str]) -> list[str]:
    """Render a tags input, wiring the session_state default if present."""
    return st_tags(
        label=label,
        text="Press enter to add more",
        value=st.session_state.get(key, []),
        suggestions=suggestions,
        maxtags=-1,
        key=key,
    )


def show_product_creation() -> None:
    st.title("Create New Product")

    # Handle pending success state from form submission (set outside form context)
    if st.session_state.get("_pending_success"):
        success_data = st.session_state._pending_success
        st.session_state.product_created = success_data["product_created"]
        st.session_state.product_created_name = success_data["product_created_name"]
        st.session_state.product_created_id = success_data["product_created_id"]
        st.session_state.product_created_slug = success_data["product_created_slug"]
        del st.session_state._pending_success

    # Show success message if product was just created
    if st.session_state.get("product_created", False):
        st.success(f"✅ Product '{st.session_state.product_created_name}' created successfully!")
        st.info(f"**Product ID:** `{st.session_state.product_created_id}`")
        st.info(f"**Product Slug:** `{st.session_state.product_created_slug}`")

        if st.button("Create Other", type="secondary", key="create_other_btn"):
            # Request form clearing on next render
            st.session_state.clear_form_requested = True
            _clear_success_state()
            st.rerun()

    # Handle "Create Other" button click - must be checked before form is rendered
    if st.session_state.get("clear_form_requested", False):
        _clear_form_fields()
        _clear_success_state()
        st.session_state.clear_form_requested = False
        # Increment form counter to force Streamlit to create a new form instance
        st.session_state.form_counter = st.session_state.get("form_counter", 0) + 1

    # Use form counter to force new form instance when clearing
    form_counter = st.session_state.get("form_counter", 0)
    form_key = f"product_form_{form_counter}"

    def get_widget_key(base_key: str) -> str:
        return f"{base_key}_{form_counter}"

    with st.form(form_key, clear_on_submit=False):
        name = st.text_input(
            "Product Name",
            placeholder="Enter product name...",
            key=get_widget_key("product_name_input"),
        )
        company_name = st.text_input(
            "Company Name",
            placeholder="Enter company name (optional)...",
            key=get_widget_key("company_name_input"),
        )
        slug = st.text_input(
            "Product Slug",
            placeholder="Enter slug (optional, will auto-generate)",
            key=get_widget_key("product_slug_input"),
        )
        domains = _render_tags(get_widget_key("domains_input"), "Domains", ["example.com", "www.example.com"])
        categories = _render_tags(
            get_widget_key("categories_input"),
            "Categories",
            [
                "Technology",
                "SaaS",
                "Privacy",
                "Finance",
                "Healthcare",
                "E-commerce",
                "Social Media",
                "Education",
            ],
        )
        crawl_base_urls = _render_tags(
            get_widget_key("crawl_urls_input"),
            "Crawl Base URLs",
            ["https://example.com/privacy", "https://example.com/terms"],
        )

        submitted = st.form_submit_button("Create Product", type="primary")

        if submitted:
            # Parse form data first
            domains_list = [domain.strip() for domain in domains if domain.strip()]
            categories_list = [category.strip() for category in categories if category.strip()]
            crawl_base_urls_list: list[str] = [
                url.strip() for url in (crawl_base_urls or []) if url.strip()
            ]
            company_name_value = company_name.strip() if company_name.strip() else None

            # Validate required fields
            errors = []

            if not name.strip():
                errors.append("Product name is required!")

            # At least one of domains or crawl_base_urls should be provided
            if not domains_list and not crawl_base_urls_list:
                errors.append("At least one domain or crawl base URL is required!")

            if errors:
                for error in errors:
                    st.error(error)
                return

            try:
                # Generate slug if not provided
                final_slug = (
                    slug.strip()
                    if slug.strip()
                    else name.lower().replace(" ", "-").replace("&", "and")
                )

                # Check if slug already exists
                with st.spinner("Checking if product already exists..."):
                    existing_product = run_async_with_retry(
                        get_product_by_slug_isolated(final_slug)
                    )

                if existing_product is not None:
                    st.error(
                        f"Product with slug '{final_slug}' already exists. Please choose a different slug."
                    )
                    return

                product = Product(
                    id=shortuuid.uuid(),
                    name=name.strip(),
                    company_name=company_name_value,
                    slug=final_slug,
                    domains=domains_list,
                    categories=categories_list,
                    crawl_base_urls=crawl_base_urls_list,
                )

                # Save product to database with retry
                with st.spinner("Creating product..."):
                    success = run_async_with_retry(create_product_isolated(product))

                if success:
                    # Store success state - use a temporary flag to set values after form context
                    st.session_state._pending_success = {
                        "product_created": True,
                        "product_created_name": product.name,
                        "product_created_id": product.id,
                        "product_created_slug": product.slug,
                    }
                    # Rerun to show success message
                    # Form fields will remain filled until user clicks "Create Other"
                    st.rerun()
                else:
                    st.error("Failed to create product. Please try again.")

            except Exception as e:
                st.error(f"Error creating product: {str(e)}")
                st.info("💡 **Troubleshooting tips:**")
                st.write("• Check that your MongoDB connection is working")
                st.write("• Verify your environment variables are set correctly")
                st.write("• Try refreshing the page and trying again")
