"""
app.py — Negotium - Investment Tracker UI (Streamlit) with Login

Run: streamlit run src/app.py

This version includes a login page where users enter their UUID key.
Loads .env for COS configuration.
"""
from __future__ import annotations

import hashlib
import hmac
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
from storage.audit import log_login_attempt
from version import get_version
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
AUTH_COOKIE_NAME = "negotium_auth"
COOKIE_MAX_AGE_DAYS = 30


def _get_cookie_secret() -> str:
    """Derive cookie secret from secrets or environment, falling back to a deterministic local secret."""
    try:
        secret = st.secrets.get("auth", {}).get("cookie_secret")
        if secret:
            return secret
    except Exception:
        pass
    import os
    return os.getenv("AUTH_COOKIE_SECRET", "negotium_cookie_secret_fallback_key")


def _generate_auth_cookie(user_key: str) -> str:
    """Generate signed cookie payload: user_key:signature."""
    secret = _get_cookie_secret()
    sig = hmac.new(secret.encode(), user_key.encode(), hashlib.sha256).hexdigest()
    return f"{user_key}:{sig}"


def _verify_auth_cookie(cookie_val: str) -> str | None:
    """Verify signed cookie and return user_key if valid, else None."""
    if not cookie_val or ":" not in cookie_val:
        return None
    user_key, sig = cookie_val.split(":", 1)
    secret = _get_cookie_secret()
    expected_sig = hmac.new(secret.encode(), user_key.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected_sig):
        return user_key
    return None


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
            background: var(--secondary-background-color, #ffffff);
            border: 1px solid var(--border-color, rgba(128,128,128,0.2));
        }
        .login-title {
            text-align: center;
            margin-bottom: 1.5rem;
            color: var(--text-color, #1a1a2e);
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
                "User Key",
                placeholder="Enter user key to access your portfolio",
                key="login_user_key",
                label_visibility="collapsed",
                type="password",
            )
            remember_me = st.checkbox("Remember me on this device", value=True, key="remember_me_cb")

            submitted = st.form_submit_button("Login", width="stretch", type="primary", disabled=not allowed)

            if submitted:
                key_val = user_key.strip() if user_key else ""
                if key_val:
                    user_name = storage.get_user_by_key(key_val)
                    if user_name:
                        log_login_attempt(key_val, success=True, username=user_name)
                        storage.set_current_user_by_key(key_val)
                        st.session_state[SESSION_LOGGED_IN] = True
                        st.session_state[SESSION_USER_KEY] = key_val
                        _reset_rate_limit()

                        # Store signed cookie for persistent session if requested
                        if remember_me:
                            try:
                                cookie_data = _generate_auth_cookie(key_val)
                                st.query_params[AUTH_COOKIE_NAME] = cookie_data
                            except Exception:
                                pass

                        st.success(f"Welcome, {user_name}!")
                        st.rerun()
                    else:
                        log_login_attempt(key_val, success=False, username=None)
                        _record_failed_attempt()
                        attempts = st.session_state.get("login_attempts", 0)
                        remaining_attempts = MAX_LOGIN_ATTEMPTS - attempts
                        if remaining_attempts > 0:
                            st.error(
                                f"Invalid user key. {remaining_attempts} attempt{'s' if remaining_attempts > 1 else ''} remaining before lockout."
                            )
                        else:
                            st.error("Invalid user key. Account locked due to multiple failed attempts.")
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
        st.markdown(
            f'<div style="text-align:center;opacity:0.5;font-size:12px;margin-top:1rem;">{get_version()}</div>',
            unsafe_allow_html=True,
        )


def main() -> None:
    """Main entry point with login flow."""
    setup_page_config()

    # Initialize theme early so login page uses correct colors
    import config as cfg_module
    from ui.colors import get_theme
    default_cfg = cfg_module.load(storage.current_user())
    theme_name = cfg_module.get_theme(default_cfg)
    T = get_theme(theme_name)
    inject_styles(T)

    # Attempt auto-login via persistent cookie if not already logged in
    if not st.session_state.get(SESSION_LOGGED_IN, False):
        cookie_val = st.query_params.get(AUTH_COOKIE_NAME)
        if cookie_val:
            user_key = _verify_auth_cookie(cookie_val)
            if user_key:
                user_name = storage.get_user_by_key(user_key)
                if user_name:
                    storage.set_current_user_by_key(user_key)
                    st.session_state[SESSION_LOGGED_IN] = True
                    st.session_state[SESSION_USER_KEY] = user_key
                    # Clear cookie from URL after successful auto-login
                    st.query_params.pop(AUTH_COOKIE_NAME, None)

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