import warnings

import streamlit as st

from src.core.config import config
from src.core.logging import setup_logging
from src.dashboard.auth import check_password, show_logout_button
from src.dashboard.components.complete_workflow import show_complete_workflow
from src.dashboard.components.crawling import show_crawling
from src.dashboard.components.deep_analysis import show_deep_analysis
from src.dashboard.components.documents_view import show_documents_view
from src.dashboard.components.embedding import show_embedding
from src.dashboard.components.product_creation import show_product_creation
from src.dashboard.components.product_view import show_product_view
from src.dashboard.components.promotion import show_promotion
from src.dashboard.components.rag import show_rag
from src.dashboard.components.summarization import show_summarization

# Suppress Streamlit ScriptRunContext warnings globally
warnings.filterwarnings("ignore", message="missing ScriptRunContext")


st.set_page_config(page_title="Clausea Dashboard", page_icon="🌊", layout="wide")

setup_logging()


def main() -> None:
    # Check authentication before showing dashboard
    if not check_password():
        return  # Login form is shown by check_password()

    # Show logout button in sidebar
    show_logout_button()
    st.sidebar.title("Navigation")

    # Create page options with id and display_name
    page_options = [
        {"id": "create_product", "display_name": "Create Product"},
        {"id": "view_products", "display_name": "View Products"},
        {"id": "view_documents", "display_name": "View Documents"},
        {"id": "complete_workflow", "display_name": "Complete Workflow"},
        {"id": "start_crawling", "display_name": "Start Crawling"},
        {"id": "generate_embeddings", "display_name": "Generate & Store Embeddings"},
        {"id": "summarization", "display_name": "Summarization"},
        {"id": "deep_analysis", "display_name": "Deep Analysis & Overview"},
        {"id": "rag", "display_name": "RAG"},
    ]

    # Only show Promotion page in development/localhost
    if config.app.is_development:
        page_options.append({"id": "promotion", "display_name": "Promotion"})

    # Check if we have a current page in session state
    current_page_id = st.session_state.get("current_page", "view_products")

    # Promotion: Handle legacy display names in session state
    # Map old display names to new page IDs for backward compatibility
    legacy_page_mapping = {
        "Create Product": "create_product",
        "View Products": "view_products",
        "View Documents": "view_documents",
        "Complete Workflow": "complete_workflow",
        "Start Crawling": "start_crawling",
        "Generate Embeddings": "generate_embeddings",
        "Generate & Store Embeddings": "generate_embeddings",
        "Summarization": "summarization",
        "Deep Analysis & Overview": "deep_analysis",
        "RAG": "rag",
        "Promotion": "promotion",
    }

    # If current_page_id is a legacy display name, convert it to page ID
    if current_page_id in legacy_page_mapping:
        current_page_id = legacy_page_mapping[current_page_id]
        st.session_state["current_page"] = current_page_id

    # If promotion page is selected but we're in production, redirect to view_products
    if current_page_id == "promotion" and not config.app.is_development:
        current_page_id = "view_products"
        st.session_state["current_page"] = current_page_id

    # Find the index of the current page
    try:
        default_index = next(
            i for i, option in enumerate(page_options) if option["id"] == current_page_id
        )
    except StopIteration:
        # If page ID is invalid, default to "View Products"
        default_index = 1
        current_page_id = "view_products"
        st.session_state["current_page"] = current_page_id

    # Extract display names for the radio button
    display_names = [option["display_name"] for option in page_options]
    selected_display_name = st.sidebar.radio("Go to", display_names, index=default_index)

    # Find the selected page option
    selected_option = next(
        option for option in page_options if option["display_name"] == selected_display_name
    )
    page_id = selected_option["id"]

    # Update session state with id
    st.session_state["current_page"] = page_id

    if page_id == "create_product":
        show_product_creation()
    elif page_id == "view_products":
        show_product_view()
    elif page_id == "view_documents":
        show_documents_view()
    elif page_id == "complete_workflow":
        show_complete_workflow()
    elif page_id == "start_crawling":
        show_crawling()
    elif page_id == "generate_embeddings":
        show_embedding()
    elif page_id == "summarization":
        show_summarization()
    elif page_id == "deep_analysis":
        show_deep_analysis()
    elif page_id == "rag":
        show_rag()
    elif page_id == "promotion":
        # Double-check we're in development (shouldn't reach here in production due to redirect above)
        if config.app.is_development:
            show_promotion()
        else:
            st.error("Promotion page is only available in development mode.")
            st.info("Redirecting to View Products...")
            st.session_state["current_page"] = "view_products"
            st.rerun()


if __name__ == "__main__":
    main()
