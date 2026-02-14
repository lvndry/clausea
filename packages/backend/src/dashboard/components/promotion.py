import os
import time
from typing import Any

import streamlit as st

from src.dashboard.db_utils import get_all_products_isolated, update_product_isolated
from src.dashboard.utils import make_api_request, run_async, run_async_with_retry
from src.models.user import UserTier


async def get_promotion_summary_async(api_url: str) -> tuple[dict[str, Any], int]:
    """Async function to get promotion summary"""
    result: tuple[dict[str, Any], int] = await make_api_request(f"{api_url}/promotion/summary")
    return result


async def run_promotion_async(
    api_url: str, endpoint: str, data: dict[str, Any] | None = None
) -> tuple[dict[str, Any], int]:
    """Async function to run promotion operations"""
    result: tuple[dict[str, Any], int] = await make_api_request(
        f"{api_url}{endpoint}", "POST", data
    )
    return result


def show_promotion() -> None:
    st.title("Data Promotion")
    st.markdown("Promote data from localhost to production database")

    # Configuration section
    st.header("Configuration")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Local Database")
        _local_uri = st.text_input(
            "Local MongoDB URI",
            value=os.getenv("MONGO_URI", ""),
            type="password",
            help="MongoDB connection string for local database",
        )

    with col2:
        st.subheader("Production Database")
        _production_uri = st.text_input(
            "Production MongoDB URI",
            value=os.getenv("PRODUCTION_MONGO_URI", ""),
            type="password",
            help="MongoDB connection string for production database",
        )

    # API Configuration
    st.subheader("API Configuration")
    api_url = st.text_input(
        "API Base URL",
        value=os.getenv("API_BASE_URL", "http://localhost:8000"),
        help="Base URL for the Clausea API",
    )

    # Promotion Summary
    st.header("Promotion Summary")

    if st.button("Get Promotion Summary", type="primary"):
        if not api_url:
            st.error("Please provide API Base URL")
            return

        try:
            with st.spinner("Fetching promotion summary..."):
                response = run_async(get_promotion_summary_async(api_url))

                if response is None:
                    st.error(
                        "Failed to fetch promotion summary. Please check your API connection and try again."
                    )
                    return

                result, status_code = response

                if status_code == 200:
                    if result.get("success"):
                        summary = result.get("data", {})

                        st.success("Promotion summary retrieved successfully!")

                        # Display summary
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.metric(
                                "Products (Local)",
                                summary.get("collections", {})
                                .get("products", {})
                                .get("local_count", 0),
                            )
                            st.metric(
                                "Products (Production)",
                                summary.get("collections", {})
                                .get("products", {})
                                .get("production_count", 0),
                            )

                        with col2:
                            st.metric(
                                "Documents (Local)",
                                summary.get("collections", {})
                                .get("documents", {})
                                .get("local_count", 0),
                            )
                            st.metric(
                                "Documents (Production)",
                                summary.get("collections", {})
                                .get("documents", {})
                                .get("production_count", 0),
                            )

                        with col3:
                            st.metric(
                                "Product Overviews (Local)",
                                summary.get("collections", {})
                                .get("product_overviews", {})
                                .get("local_count", 0),
                            )
                            st.metric(
                                "Product Overviews (Production)",
                                summary.get("collections", {})
                                .get("product_overviews", {})
                                .get("production_count", 0),
                            )

                        # Store summary in session state
                        st.session_state["promotion_summary"] = summary

                        # Show detailed summary
                        with st.expander("Detailed Summary"):
                            st.json(summary)
                    else:
                        st.error(f"Failed to get summary: {result.get('message', 'Unknown error')}")
                else:
                    st.error(f"API request failed with status {status_code}")

        except Exception as e:
            st.error(f"Error fetching promotion summary: {str(e)}")

    # Promotion Actions
    st.header("Promotion Actions")

    # Dry Run Section
    st.subheader("Dry Run")
    st.info(
        "A dry run will show you what would be promoted without actually performing the promotion."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Dry Run - All Data"):
            run_promotion(api_url, "/promotion/dry-run", "Full dry run promotion")

    with col2:
        if st.button("Dry Run - Products Only"):
            run_promotion(
                api_url,
                "/promotion/promote-products",
                "Products dry run promotion",
                {"dry_run": True},
            )

    with col3:
        if st.button("Dry Run - Documents Only"):
            run_promotion(
                api_url,
                "/promotion/promote-documents",
                "Documents dry run promotion",
                {"dry_run": True},
            )

    # Actual Promotion Section
    st.subheader("Execute Promotion")
    st.warning("⚠️ This will actually promote data to production. Make sure you have a backup!")

    # Confirmation checkbox
    promotion_confirmed = st.checkbox(
        "I understand this will promote data to production and I have a backup"
    )

    if promotion_confirmed:
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Promote All Data", type="secondary"):
                run_promotion(
                    api_url,
                    "/promotion/execute",
                    "Full promotion",
                    {"dry_run": False},
                )

        with col2:
            if st.button("Promote Products Only", type="secondary"):
                run_promotion(
                    api_url,
                    "/promotion/promote-products",
                    "Products promotion",
                    {"dry_run": False},
                )

        with col3:
            if st.button("Promote Documents Only", type="secondary"):
                run_promotion(
                    api_url,
                    "/promotion/promote-documents",
                    "Documents promotion",
                    {"dry_run": False},
                )
    else:
        st.info("Please confirm that you understand the promotion will modify production data.")

    # Promotion History
    if "promotion_results" in st.session_state:
        st.header("Promotion Results")

        for result in st.session_state["promotion_results"]:
            with st.expander(f"{result['timestamp']} - {result['action']}"):
                st.json(result["data"])


def run_promotion(
    api_url: str, endpoint: str, action: str, data: dict[str, Any] | None = None
) -> None:
    """Helper function to run promotion operations"""
    if not api_url:
        st.error("Please provide API Base URL")
        return

    try:
        with st.spinner(f"Running {action}..."):
            response = run_async(run_promotion_async(api_url, endpoint, data))

            if response is None:
                st.error(f"Failed to run {action}. Please check your API connection and try again.")
                return

            result, status_code = response

            if status_code == 200:
                if result.get("success"):
                    st.success(f"{action} completed successfully!")

                    # Store result in session state
                    if "promotion_results" not in st.session_state:
                        st.session_state["promotion_results"] = []

                    st.session_state["promotion_results"].append(
                        {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "action": action,
                            "data": result.get("data", {}),
                        }
                    )

                    # Display results
                    st.subheader(f"Results for {action}")
                    display_promotion_results(result.get("data", {}))
                else:
                    st.error(f"{action} failed: {result.get('message', 'Unknown error')}")
            else:
                st.error(f"API request failed with status {status_code}")

    except Exception as e:
        st.error(f"Error running {action}: {str(e)}")


def display_promotion_results(data: dict[str, Any]) -> None:
    """Display promotion results in a formatted way"""
    if not data:
        st.info("No data to display")
        return

    # Summary section
    if "summary" in data:
        st.subheader("Summary")
        summary = data["summary"]

        if isinstance(summary, dict) and "collections" in summary:
            collections = summary["collections"]
            if not isinstance(collections, dict):
                st.warning("Summary collections data is not in expected format")
            else:
                col1, col2, col3 = st.columns(3)

                with col1:
                    products = collections.get("products", {})
                    if isinstance(products, dict):
                        st.metric("Products (Local)", products.get("local_count", 0))
                        st.metric("Products (Production)", products.get("production_count", 0))
                    else:
                        st.metric("Products", products if isinstance(products, int | float) else 0)

                with col2:
                    documents = collections.get("documents", {})
                    if isinstance(documents, dict):
                        st.metric("Documents (Local)", documents.get("local_count", 0))
                        st.metric("Documents (Production)", documents.get("production_count", 0))
                    else:
                        st.metric(
                            "Documents", documents if isinstance(documents, int | float) else 0
                        )

                with col3:
                    product_overviews = collections.get("product_overviews", {})
                    if isinstance(product_overviews, dict):
                        st.metric(
                            "Product Overviews (Local)",
                            product_overviews.get("local_count", 0),
                        )
                        st.metric(
                            "Product Overviews (Production)",
                            product_overviews.get("production_count", 0),
                        )
                    else:
                        st.metric(
                            "Product Overviews",
                            product_overviews if isinstance(product_overviews, int | float) else 0,
                        )

    # Promotion results
    st.subheader("Promotion Results")

    # Check if this is a single collection result or full promotion result
    # Support both old structure (promoted/skipped) and new structure (local_count/deleted_count/inserted_count)
    is_old_structure = "promoted" in data and "skipped" in data
    is_new_structure = "local_count" in data or "deleted_count" in data or "inserted_count" in data

    if is_old_structure or is_new_structure:
        # Single collection result (e.g., documents only, products only)
        result = data
        collection_name = "Promotion"  # Generic name for single collection

        with st.expander(f"{collection_name}"):
            if is_new_structure:
                # New structure: complete replacement
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("Local Count", result.get("local_count", 0))

                with col2:
                    st.metric("Deleted (Production)", result.get("deleted_count", 0))

                with col3:
                    st.metric("Inserted (Production)", result.get("inserted_count", 0))

                with col4:
                    st.metric("Errors", len(result.get("errors", [])))

                if result.get("errors"):
                    st.error("Errors occurred:")
                    for error in result["errors"]:
                        st.text(f"• {error}")

                if result.get("dry_run"):
                    st.info("This was a dry run - no actual data was promoted")
                else:
                    st.success("Data was successfully replaced in production")
            else:
                # Old structure: diff-based promotion
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Promoted", result.get("promoted", 0))

                with col2:
                    st.metric("Skipped", result.get("skipped", 0))

                with col3:
                    st.metric("Errors", len(result.get("errors", [])))

                if result.get("errors"):
                    st.error("Errors occurred:")
                    for error in result["errors"]:
                        st.text(f"• {error}")

                if result.get("dry_run"):
                    st.info("This was a dry run - no actual data was promoted")
                else:
                    st.success("Data was successfully promoted")
    else:
        # Full promotion result with multiple collections
        for collection_name, result_value in data.items():
            if (
                collection_name != "summary"
                and collection_name != "dry_run"
                and collection_name != "timestamp"
            ):
                result = result_value

                # Check if result is a dictionary before processing
                # Type checker may flag this, but runtime values can be any type
                # Using getattr to avoid type checker false positive
                if not hasattr(result, "get") or not isinstance(result, dict):  # noqa: PLR1702
                    st.error(
                        f"**Invalid data structure for '{collection_name}' collection**\n\n"
                        f"- **Expected:** Dictionary with promotion results\n"
                        f"- **Got:** {type(result).__name__}\n"
                        f"- **Value:** `{result}`\n\n"
                        f"This field should contain a dictionary with keys like 'local_count', "
                        f"'deleted_count', 'inserted_count', 'errors' (new structure) or "
                        f"'promoted', 'skipped', 'errors' (old structure), but instead received a {type(result).__name__}."
                    )
                    with st.expander(f"🔍 Debug: Raw value for '{collection_name}'"):
                        st.json(result)
                    continue

                # Handle case where result might not have expected structure
                # Support both old structure (promoted/skipped) and new structure (local_count/deleted_count/inserted_count)
                try:
                    with st.expander(f"{collection_name.title()} Promotion"):
                        # Check for new structure first
                        if (
                            "local_count" in result
                            or "deleted_count" in result
                            or "inserted_count" in result
                        ):
                            # New structure: complete replacement
                            col1, col2, col3, col4 = st.columns(4)

                            with col1:
                                st.metric("Local Count", result.get("local_count", 0))

                            with col2:
                                st.metric("Deleted (Production)", result.get("deleted_count", 0))

                            with col3:
                                st.metric("Inserted (Production)", result.get("inserted_count", 0))

                            with col4:
                                errors = result.get("errors", [])
                                st.metric("Errors", len(errors))

                            if errors:
                                st.error("Errors occurred:")
                                for error in errors:
                                    st.text(f"• {error}")

                            if result.get("dry_run"):
                                st.info("This was a dry run - no actual data was promoted")
                            else:
                                st.success("Data was successfully replaced in production")
                        elif "promoted" in result or "skipped" in result:
                            # Old structure: diff-based promotion
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                promoted_count = result.get("promoted", 0)
                                st.metric("Promoted", promoted_count)

                            with col2:
                                skipped_count = result.get("skipped", 0)
                                st.metric("Skipped", skipped_count)

                            with col3:
                                errors = result.get("errors", [])
                                st.metric("Errors", len(errors))

                            if errors:
                                st.error("Errors occurred:")
                                for error in errors:
                                    st.text(f"• {error}")

                            if result.get("dry_run"):
                                st.info("This was a dry run - no actual data was promoted")
                            else:
                                st.success("Data was successfully promoted")
                        else:
                            # Unknown structure - show raw data
                            st.warning("Unknown promotion result structure")
                            st.json(result)
                except (AttributeError, TypeError, KeyError) as e:
                    # Handle case where result structure doesn't match expectations
                    error_type = type(e).__name__
                    error_details = str(e)

                    st.error(
                        f"**Error processing '{collection_name}' promotion results**\n\n"
                        f"- **Error Type:** `{error_type}`\n"
                        f"- **Error Details:** `{error_details}`\n"
                        f"- **Collection Name:** `{collection_name}`\n\n"
                        f"The data structure for this collection doesn't match the expected format. "
                        f"Expected a dictionary with keys: 'local_count', 'deleted_count', 'inserted_count', 'errors' "
                        f"(new structure) or 'promoted', 'skipped', 'errors' (old structure)."
                    )
                    with st.expander(f"🔍 Debug: Raw data structure for '{collection_name}'"):
                        st.json(result)
                        st.code(
                            f"Type: {type(result).__name__}\nKeys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}"
                        )

    # If we couldn't parse the data structure, show raw data for debugging
    if isinstance(data, dict) and not any(
        [
            "promoted" in data,
            "local_count" in data,
            "summary" in data,
            any(
                isinstance(v, dict)
                and (
                    "promoted" in v or "skipped" in v or "local_count" in v or "deleted_count" in v
                )
                for v in data.values()
                if isinstance(v, dict)
            ),
        ]
    ):
        with st.expander("Raw Promotion Data (Debug)"):
            st.json(data)

    # Tier Visibility Management Section
    st.write("---")
    st.header("Tier Visibility Management")
    st.markdown("Manage which user tiers can access specific products")

    # Get current products
    try:
        with st.spinner("Loading products..."):
            products = run_async_with_retry(get_all_products_isolated())

        if products is None:
            st.error("Failed to load products from database.")
            return

        if not products:
            st.info("No products found. Create some products first!")
            return

        st.success(f"✅ Loaded {len(products)} products")

        # Bulk tier visibility operations
        st.subheader("Bulk Tier Visibility Operations")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Make All Products Accessible to All Tiers**")
            if st.button("🔄 Reset All to Free", type="secondary"):
                try:
                    with st.spinner("Updating all products..."):
                        updated_count = 0
                        for product in products:
                            product.visible_to_tiers = [
                                UserTier.FREE,
                                UserTier.BUSINESS,
                                UserTier.ENTERPRISE,
                            ]
                            success = run_async_with_retry(update_product_isolated(product))
                            if success:
                                updated_count += 1

                        if updated_count == len(products):
                            st.success(
                                f"✅ All {updated_count} products are now accessible to all tiers!"
                            )
                        else:
                            st.warning(f"⚠️ Updated {updated_count}/{len(products)} products")
                except Exception as e:
                    st.error(f"Error updating products: {str(e)}")

        with col2:
            st.write("**Add Tier Visibility Fields to Missing Products**")
            if st.button("🔧 Fix Missing Tier Fields", type="secondary"):
                try:
                    with st.spinner("Checking for missing tier fields..."):
                        missing_tier_fields = [
                            p
                            for p in products
                            if not hasattr(p, "visible_to_tiers") or not p.visible_to_tiers
                        ]

                        if not missing_tier_fields:
                            st.info("✅ All products already have tier visibility fields!")
                        else:
                            st.info(
                                f"Found {len(missing_tier_fields)} products without tier fields"
                            )

                            for product in missing_tier_fields:
                                product.visible_to_tiers = [
                                    UserTier.FREE,
                                    UserTier.BUSINESS,
                                    UserTier.ENTERPRISE,
                                ]
                                run_async_with_retry(update_product_isolated(product))

                            st.success(
                                f"✅ Added tier fields to {len(missing_tier_fields)} products!"
                            )
                except Exception as e:
                    st.error(f"Error fixing tier fields: {str(e)}")

        # Strategic tier assignments
        st.subheader("Strategic Tier Assignments")

        # Define product categories for strategic gating
        st.write("**Premium Content Strategy**")
        st.info("Make high-value products premium-only to drive conversions")

        # Tier visibility statistics
        st.subheader("Current Tier Visibility Statistics")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
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
            premium_only = len(
                [
                    p
                    for p in products
                    if hasattr(p, "visible_to_tiers") and UserTier.FREE not in p.visible_to_tiers
                ]
            )
            st.metric("Premium Only", premium_only, delta=f"{premium_only}/{len(products)}")

    except Exception as e:
        st.error(f"Error loading products: {str(e)}")
        st.write("Please check your database connection and try again.")
