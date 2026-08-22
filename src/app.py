"""
app.py — Negotium - Investment Tracker UI (Streamlit)

Run: streamlit run src/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg_module
from ui.dashboard import render_dashboard
from ui.helpers import detect_currency
from ui.runtime import init_runtime
from ui.sidebar import render_sidebar

st.set_page_config(
    page_title="Negotium",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

cfg, storage, _theme_name, T, today = init_runtime()
start_date_cfg = cfg_module.get_start_date(cfg)
base_ccy = render_sidebar(cfg, storage, T, today, start_date_cfg, detect_currency)
render_dashboard(cfg, storage, T, today, start_date_cfg, base_ccy)
