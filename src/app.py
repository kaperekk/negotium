"""
app.py — Negotium - Investment Tracker UI (Streamlit) with Login

Run: streamlit run src/app.py

This version includes a login page where users enter their UUID key.
Loads .env for COS configuration.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Load .env for COS configuration
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

import storage
from app_core import (
    inject_styles,
    inject_theme_veil,
    init_runtime_with_user,
    render_main_app,
    setup_page_config,
)

SESSION_LOGGED_IN = "negotium_logged_in"
SESSION_USER_KEY = "negotium_user_key"


def render_login_page() -> None:
    """Render login page."""
    st.markdown(
        """
        <style>
        .login-container {
            max-width: 400px;
            margin: 4rem auto;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.1);
        }
        .login-title {
            text-align: center;
            margin-bottom: 1.5rem;
            color: #1a1a2e;
        }
        .login-button {
            width: 100%;
            margin-top: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            '<div class="login-container">'
            '<h1 class="login-title">🔐 Negotium Login</h1>'
            '</div>',
            unsafe_allow_html=True,
        )

        user_key = st.text_input(
            "User Key (UUID)",
            placeholder="Enter your user UUID key to access your portfolio",
            key="login_user_key",
            label_visibility="collapsed",
        )

        if st.button("Login", key="login_button", width="stretch", type="primary"):
            if user_key and user_key.strip():
                user_name = storage.get_user_by_key(user_key.strip())
                if user_name:
                    storage.set_current_user_by_key(user_key.strip())
                    st.session_state[SESSION_LOGGED_IN] = True
                    st.session_state[SESSION_USER_KEY] = user_key.strip()
                    st.success(f"Welcome, {user_name}!")
                    st.rerun()
                else:
                    st.error("Invalid user key. Please check and try again.")
            else:
                st.error("Please enter your user key.")

        st.markdown('</div>', unsafe_allow_html=True)


def main() -> None:
    """Main entry point with login flow."""
    setup_page_config()

    if not st.session_state.get(SESSION_LOGGED_IN, False):
        render_login_page()
    else:
        # Initialize runtime with logged-in user's key
        user_key = st.session_state.get(SESSION_USER_KEY)
        cfg, storage_mod, _theme_name, T, today = init_runtime_with_user(user_key)

        inject_styles(T)
        inject_theme_veil(T)
        render_main_app(cfg, storage_mod, T, today)


if __name__ == "__main__":
    main()