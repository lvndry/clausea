import streamlit as st

from src.dashboard.db_utils import get_all_products_isolated
from src.dashboard.utils import run_async
from src.rag import get_answer


def show_rag() -> None:
    st.title("RAG Question Answering")

    # Get list of products from the database
    products = run_async(get_all_products_isolated())

    if products is None:
        st.error("Error fetching products")
        return

    # Product selection
    selected_product = st.selectbox("Select a product", [product.slug for product in products])

    # Question input
    question = st.text_area("Enter your question about the product:", height=100)

    if st.button("Get Answer"):
        if question:
            with st.spinner("Generating answer..."):
                try:
                    answer = run_async(get_answer(question, selected_product))
                    st.write("Answer:")
                    st.write(answer)
                except Exception as e:
                    st.error(f"Error generating answer: {str(e)}")
        else:
            st.warning("Please enter a question.")
