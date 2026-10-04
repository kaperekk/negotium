"""
app_core.py — Shared core application logic for Negotium.

Used by both app.py (with login) and app_local.py (direct access).
"""
from __future__ import annotations

import time
from datetime import date

import streamlit as st

import config as cfg_module
import ledger_core
import storage
from ui.dashboard import render_dashboard
from ui.sidebar import render_sidebar
from ui.styles import (
    build_app_styles,
    build_holdings_styles,
    build_late_theme_override,
    build_metric_card_styles,
    build_theme_veil,
    build_toggle_button_styles,
)
from ui.colors import get_theme
from ui.bootstrap import configure_import_logging, ensure_project_context
from storage.context import LOCAL_USER


def init_runtime_with_user(user_key: str | None = None) -> tuple[dict, object, str, str, date]:
    """Initialize runtime with the given user key (or default)."""
    ensure_project_context()
    configure_import_logging()

    if user_key:
        storage.set_current_user_by_key(user_key)
    else:
        storage.set_current_user(LOCAL_USER)

    current_user = storage.current_user()
    cfg = cfg_module.load(current_user)
    if "theme" not in st.session_state:
        st.session_state["theme"] = cfg_module.get_theme(cfg)
    if "log_scale" not in st.session_state:
        st.session_state["log_scale"] = cfg_module.get_log_scale(cfg)

    theme = get_theme(st.session_state["theme"])
    return cfg, storage, st.session_state["theme"], theme, date.today()


def inject_styles(T: str) -> None:
    """Inject all theme-dependent styles."""
    st.markdown(
        build_app_styles(T)
        + build_late_theme_override(T)
        + build_metric_card_styles(T)
        + build_toggle_button_styles(T)
        + build_holdings_styles(T),
        unsafe_allow_html=True,
    )


def inject_theme_veil(T: str) -> None:
    """Inject theme transition veil if needed."""
    _fade_ts = st.session_state.pop("theme_fade", None)
    if _fade_ts is not None and (time.time() - _fade_ts) < 3:
        st.markdown(build_theme_veil(T), unsafe_allow_html=True)


def render_main_app(cfg, storage_mod, T, today) -> None:
    """Render the main dashboard application."""
    data_start_date = ledger_core.first_transaction_date() or today
    base_ccy = render_sidebar(cfg, storage_mod, T, today, data_start_date)
    render_dashboard(cfg, storage_mod, T, today, data_start_date, base_ccy)


def setup_page_config() -> None:
    """Configure Streamlit page settings."""
    st.set_page_config(
        page_title="Negotium",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )