"""Deep analysis component using Repository pattern."""

import streamlit as st

from src.core.database import get_db
from src.core.logging import get_logger
from src.dashboard.db_utils import get_all_products_isolated
from src.dashboard.utils import run_async
from src.models.document import ProductDeepAnalysis
from src.services.service_factory import create_services
from src.summarizer import generate_product_deep_analysis

logger = get_logger(__name__)


def show_deep_analysis() -> None:
    st.title("🔬 Deep Analysis & Overview")

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
    preselected_product = st.session_state.get("selected_product_for_deep_analysis", None)
    default_index = 0

    if preselected_product:
        # Find the index of the preselected product
        for i, product in enumerate(products):
            if product.id == preselected_product:
                default_index = i
                break

    selected_product_key = st.selectbox(
        "Select Product for Deep Analysis",
        options=list(product_options.keys()),
        index=default_index,
        help="Choose which product's documents you want to analyze deeply",
    )

    selected_product = product_options[selected_product_key]

    # Show product details
    st.write("---")
    st.subheader(f"Product: {selected_product.name}")

    # Check for existing deep analysis
    async def check_existing_analysis() -> ProductDeepAnalysis | None:
        async with get_db() as db:
            product_svc, _ = create_services()
            return await product_svc.get_product_deep_analysis(db, selected_product.slug)

    existing_analysis = run_async(check_existing_analysis())

    if existing_analysis:
        st.success("✅ Deep Analysis Available")

        # Display Analysis
        st.subheader("📊 Executive Summary")

        # Display Cross Document Analysis
        if existing_analysis.cross_document_analysis:
            st.write("### 🔗 Cross-Document Insights")

            if existing_analysis.cross_document_analysis.contradictions:
                st.write("**Contradictions:**")
                for item in existing_analysis.cross_document_analysis.contradictions:
                    st.error(f"• {item.description}")

            if existing_analysis.cross_document_analysis.information_gaps:
                st.write("**Information Gaps:**")
                for item in existing_analysis.cross_document_analysis.information_gaps:
                    st.warning(f"• {str(item)}")

        # Display Business Impact
        if existing_analysis.business_impact:
            st.write("### 💼 Business Impact")

            st.write("**For Individuals:**")
            individuals = existing_analysis.business_impact.for_individuals
            st.write(f"Risk Level: {individuals.privacy_risk_level}")
            st.write(f"Exposure: {individuals.data_exposure_summary}")
            if individuals.recommended_actions:
                st.write("Recommended Actions:")
                for action in individuals.recommended_actions:
                    st.write(f"• {action.action} (Priority: {action.priority})")

            st.write("**For Businesses:**")
            businesses = existing_analysis.business_impact.for_businesses
            st.write(f"Financial Impact: {businesses.financial_impact}")
            st.write(f"Reputational Risk: {businesses.reputational_risk}")
            if businesses.recommended_actions:
                st.write("Recommended Actions:")
                for action in businesses.recommended_actions:
                    st.write(f"• {action.action} (Priority: {action.priority})")

        # Display Risk Prioritization
        if existing_analysis.risk_prioritization:
            st.write("### ⚠️ Risk Prioritization")
            if existing_analysis.risk_prioritization.critical:
                for risk in existing_analysis.risk_prioritization.critical:
                    st.error(f"**CRITICAL:** {risk}")
            if existing_analysis.risk_prioritization.high:
                for risk in existing_analysis.risk_prioritization.high:
                    st.warning(f"**HIGH:** {risk}")
            if existing_analysis.risk_prioritization.medium:
                for risk in existing_analysis.risk_prioritization.medium:
                    st.info(f"**MEDIUM:** {risk}")

        if st.button("🔄 Regenerate Analysis"):
            _generate_analysis(selected_product.slug)

    else:
        st.info("No deep analysis found for this product.")
        if st.button("🚀 Generate Deep Analysis"):
            _generate_analysis(selected_product.slug)


async def generate_deep_analysis_wrapper(product_slug: str) -> bool:
    """Generate deep analysis using repository pattern with context manager.

    This creates a fresh database session in the current event loop,
    solving the threading issues with Streamlit.
    """
    try:
        async with get_db() as db:
            # Create services with fresh repositories
            product_svc, doc_svc = create_services()

            # Generate analysis
            await generate_product_deep_analysis(
                db,
                product_slug,
                force_regenerate=True,
                product_svc=product_svc,
                document_svc=doc_svc,
            )
            return True
    except Exception as e:
        logger.error(f"Error generating deep analysis: {e}", exc_info=True)
        return False


def _generate_analysis(product_slug: str) -> None:
    with st.spinner(f"Generating deep analysis for {product_slug}... This may take a few minutes."):
        # Deep analysis can take 5-15 minutes, so use a longer timeout (20 minutes)
        result = run_async(generate_deep_analysis_wrapper(product_slug), timeout=1200)

        if result:
            st.success("✅ Deep analysis generated successfully!")
            st.rerun()
        else:
            st.error("Failed to generate analysis. Please check the logs.")
