"""Authentication gate — validates UUID key against data/keys.json."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from storage.context import DATA_ROOT


KEYS_FILE = DATA_ROOT / "keys.json"


def load_keys() -> dict[str, str]:
    """Return {key: user_id} mapping."""
    if KEYS_FILE.exists():
        return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    return {}


def render_auth_gate() -> str | None:
    """
    Show key input screen. Returns user_id if authenticated, None otherwise.
    Sets st.session_state.user_id on success.
    """
    keys = load_keys()

    st.set_page_config(
        page_title="Negotium — Access Required",
        page_icon="🔐",
        layout="centered",
    )

    st.markdown(
        """
        <style>
        .auth-container { max-width: 480px; margin: 4rem auto; padding: 2rem; }
        .auth-title { font-size: 1.5rem; font-weight: 600; margin-bottom: 0.5rem; }
        .auth-subtitle { color: #888; margin-bottom: 2rem; }
        .key-hint { font-size: 0.85rem; color: #666; margin-top: 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.markdown('<div class="auth-title">🔐 Negotium</div>', unsafe_allow_html=True)
    st.markdown('<div class="auth-subtitle">Enter your access key to continue</div>', unsafe_allow_html=True)

    key_input = st.text_input(
        "Access Key",
        type="password",
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        label_visibility="collapsed",
        key="auth_key_input",
    )

    if key_input:
        key = key_input.strip()
        user_id = keys.get(key)
        if user_id:
            st.session_state["user_id"] = user_id
            st.success("Access granted")
            st.rerun()
        else:
            st.error("Invalid key. Please check and try again.")

    st.markdown(
        '<div class="key-hint">Your key is a UUID (36 characters). '
        'Contact the administrator if you need one.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    return None


def require_auth() -> str:
    """
    Call at app startup. Returns user_id.
    Shows auth gate and stops execution if not authenticated.
    """
    if "user_id" in st.session_state:
        return st.session_state["user_id"]

    render_auth_gate()
    st.stop()