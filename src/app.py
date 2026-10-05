"""
app.py — Negotium - Investment Tracker UI (Streamlit) with Login

Run: streamlit run src/app.py

This version includes a login page where users enter their UUID key.
Loads .env for COS configuration.
"""
from __future__ import annotations

import sys
import time
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

# Rate limiting config
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 300  # 5 minutes


def _check_rate_limit() -> tuple[bool, int]:
    """Check if login is rate limited. Returns (allowed, remaining_seconds)."""
    now = time.time()
    attempts = st.session_state.get("login_attempts", 0)
    last_attempt = st.session_state.get("login_last_attempt", 0)
    locked_until = st.session_state.get("login_locked_until", 0)

    if now < locked_until:
        return False, int(locked_until - now)

    # Reset attempts if enough time passed since last attempt
    if now - last_attempt > LOCKOUT_DURATION_SECONDS:
        st.session_state["login_attempts"] = 0
        attempts = 0

    if attempts >= MAX_LOGIN_ATTEMPTS:
        lockout_end = last_attempt + LOCKOUT_DURATION_SECONDS
        st.session_state["login_locked_until"] = lockout_end
        return False, int(lockout_end - now)

    return True, 0


def _record_failed_attempt() -> None:
    """Record a failed login attempt."""
    now = time.time()
    attempts = st.session_state.get("login_attempts", 0) + 1
    st.session_state["login_attempts"] = attempts
    st.session_state["login_last_attempt"] = now
    if attempts >= MAX_LOGIN_ATTEMPTS:
        st.session_state["login_locked_until"] = now + LOCKOUT_DURATION_SECONDS


def _reset_rate_limit() -> None:
    """Reset rate limit on successful login."""
    st.session_state["login_attempts"] = 0
    st.session_state["login_last_attempt"] = 0
    st.session_state["login_locked_until"] = 0


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
        .rate-limit-msg {
            color: #dc3545;
            text-align: center;
            margin-top: 1rem;
            font-size: 14px;
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

        # Check rate limit
        allowed, remaining = _check_rate_limit()
        if not allowed:
            mins = remaining // 60
            secs = remaining % 60
            st.markdown(
                f'<div class="rate-limit-msg">Too many failed attempts. '
                f'Try again in {mins}m {secs}s.</div>',
                unsafe_allow_html=True,
            )
            st.stop()

        # Native Streamlit form - fast, no page reload
        with st.form("login_form"):
            user_key = st.text_input(
                "User Keyanythin else to add",
                placeholder="Enter user key to access your portfolio",
                key="login_user_key",
                label_visibility="collapsed",
                type="password",
            )

            submitted = st.form_submit_button("Login", width="stretch", type="primary", disabled=not allowed)

            if submitted:
                if user_key and user_key.strip():
                    user_name = storage.get_user_by_key(user_key.strip())
                    if user_name:
                        storage.set_current_user_by_key(user_key.strip())
                        st.session_state[SESSION_LOGGED_IN] = True
                        st.session_state[SESSION_USER_KEY] = user_key.strip()
                        _reset_rate_limit()
                        st.success(f"Welcome, {user_name}!")
                        st.rerun()
                    else:
                        _record_failed_attempt()
                        st.error("Invalid user key. Please check and try again.")
                else:
                    st.error("Please enter your user key.")

        # Inject autocomplete attributes for password managers
        st.html("""
        <script>
            // Run after Streamlit renders
            setTimeout(function() {
                const form = document.querySelector('form[data-testid="stForm"]');
                if (form) {
                    const input = form.querySelector('input[type="password"]');
                    if (input) {
                        input.setAttribute('autocomplete', 'current-password');
                        input.setAttribute('name', 'password');
                    }
                    // Ensure form has proper attributes for password managers
                    form.setAttribute('method', 'post');
                    form.setAttribute('action', '');
                }
            }, 100);
        </script>
        """)

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