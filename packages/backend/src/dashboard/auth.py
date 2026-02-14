"""Authentication module for Streamlit dashboard."""

import hashlib
import os
from collections.abc import Callable

import streamlit as st

from src.core.logging import get_logger

logger = get_logger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 (simple hashing for admin dashboard)."""
    return hashlib.sha256(password.encode()).hexdigest()


def get_dashboard_password() -> str | None:
    """Get dashboard password from environment variable."""
    return os.getenv("DASHBOARD_PASSWORD")


def check_password() -> bool:
    """
    Check if user has entered the correct password.

    Returns:
        True if password is correct, False otherwise
    """
    # Check if already authenticated
    if st.session_state.get("authenticated", False):
        return True

    # Get password from config
    correct_password = get_dashboard_password()

    # If no password is set, allow access (development mode)
    if not correct_password:
        logger.warning("No dashboard password set - allowing access (development mode)")
        st.session_state["authenticated"] = True
        return True

    # Hash the correct password for comparison
    correct_password_hash = hash_password(correct_password)

    # Show login form
    st.title("🔐 Clausea Dashboard Login")
    st.markdown("---")

    # Create login form
    with st.form("login_form"):
        st.markdown("### Enter Dashboard Password")
        password_input = st.text_input(
            "Password",
            type="password",
            placeholder="Enter dashboard password",
            autocomplete="off",
        )
        submit_button = st.form_submit_button("Login", type="primary")

        if submit_button:
            if password_input:
                # Hash input password and compare
                input_hash = hash_password(password_input)
                if input_hash == correct_password_hash:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("❌ Incorrect password. Please try again.")
                    logger.warning("Failed login attempt")
            else:
                st.warning("Please enter a password")

    # Show help text
    st.info("💡 Contact your administrator if you need access to the dashboard.")

    return False


def require_auth(func: Callable) -> Callable:
    """
    Decorator to require authentication for a Streamlit page/function.

    Usage:
        @require_auth
        def show_my_page():
            st.title("My Page")
    """

    def wrapper(*args, **kwargs):
        if not check_password():
            return  # Login form is shown by check_password()
        return func(*args, **kwargs)

    return wrapper


def logout() -> None:
    """Log out the current user."""
    if "authenticated" in st.session_state:
        del st.session_state["authenticated"]
    logger.info("User logged out")
    st.rerun()


def show_logout_button() -> None:
    """Show logout button in sidebar."""
    if st.session_state.get("authenticated", False):
        st.sidebar.markdown("---")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            logout()
