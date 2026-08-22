"""Runtime bootstrap for the Streamlit application."""

from __future__ import annotations

from datetime import date

import streamlit as st

import config as cfg_module
import storage
from ui.bootstrap import configure_import_logging, ensure_project_context
from ui.theme import get_theme


def init_runtime() -> tuple[dict, dict, str, str, date]:
    """Prepare project state, config, theme and logger for the UI."""
    ensure_project_context()
    configure_import_logging()

    cfg = cfg_module.load()
    if "theme" not in st.session_state:
        st.session_state["theme"] = cfg_module.get_theme(cfg)

    theme = get_theme(st.session_state["theme"])
    return cfg, storage, st.session_state["theme"], theme, date.today()
