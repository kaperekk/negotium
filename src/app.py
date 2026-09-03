"""
app.py — Negotium - Investment Tracker UI (Streamlit)

Run: streamlit run src/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

import ledger_core
from ui.dashboard import render_dashboard
from ui.helpers import detect_currency
from ui.runtime import init_runtime
from ui.sidebar import render_sidebar
from ui.styles import build_app_styles

st.set_page_config(
    page_title="Negotium",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

cfg, storage, _theme_name, T, today = init_runtime()
st.markdown(build_app_styles(T), unsafe_allow_html=True)
data_start_date = ledger_core.first_transaction_date() or today
base_ccy = render_sidebar(cfg, storage, T, today, data_start_date, detect_currency)
render_dashboard(cfg, storage, T, today, data_start_date, base_ccy)
