"""
app.py —  Negotium - Investment Tracker UI (Streamlit)

Run: streamlit run src/app.py
"""
from __future__ import annotations

import sys
import time
import json
import html
import logging
from pathlib import Path
from datetime import date, datetime, timedelta

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg_module
import storage
from ticker_data import ensure_batch, get_price, get_fx_rate, get_ticker_name
from portfolio import FX_TICKERS
from transactions import (
    add_transaction, get_all_transactions, get_all_tickers,
    set_account_operation, delete_transaction, update_transaction,
    get_ticker_history, rebuild_balance, compute_cagr, compute_irr,
)
from portfolio import build_portfolio, snapshots_to_series
from xtb_import import import_xtb
from bossa_import import import_bossa
from manual_import import import_manual

BROKERS = ["XTB", "BOSSA", "Custom"]
BROKER_CURRENCIES = {"XTB": ["EUR", "PLN", "USD"], "BOSSA": ["EUR", "PLN", "Many"]}

THEMES = {
    "dark": {
        "card_bg": "rgba(14,17,23,0.6)",
        "border": "rgba(255,255,255,0.08)",
        "border_hover": "rgba(255,255,255,0.2)",
        "border_active": "rgba(255,255,255,0.18)",
        "border_strong": "#30363D",
        "text": "#E6EDF3",
        "text_cell": "#C9D1D9",
        "text_muted": "#8B949E",
        "text_faint": "rgba(255,255,255,0.5)",
        "panel_bg": "#161B22",
        "hr": "#21262D",
        "accent": "#6C63FF",
        "accent_tag_bg": "rgba(108,99,255,0.2)",
        "accent_tag_border": "rgba(108,99,255,0.4)",
        "accent_tag_hover": "rgba(108,99,255,0.3)",
        "card_btn_active": "rgba(255,255,255,0.04)",
        "card_faint": "rgba(255,255,255,0.03)",
        "chart_grid": "rgba(48,54,61,0.6)",
        "chart_zeroline": "rgba(48,54,61,0.8)",
        "hover_bg": "rgba(22,27,34,0.95)",
        "plotly_template": "plotly_dark",
        "page_bg": "#0E1117",
        "range_bg": "rgba(255,255,255,0.05)",
        "range_active": "rgba(108,99,255,0.3)",
        "table_border": "#333",
        "table_header_border": "#555",
        "table_hover": "rgba(255,255,255,0.05)",
        "table_text": "#e0e0e0",
        "holdings_bar_bg": "rgba(255,255,255,0.05)",
    },
    "light": {
        "card_bg": "rgba(255,255,255,0.9)",
        "border": "rgba(0,0,0,0.10)",
        "border_hover": "rgba(0,0,0,0.20)",
        "border_active": "rgba(0,0,0,0.16)",
        "border_strong": "#D0D7DE",
        "text": "#1F2328",
        "text_cell": "#3B4045",
        "text_muted": "#656D76",
        "text_faint": "rgba(0,0,0,0.45)",
        "panel_bg": "#F6F8FA",
        "hr": "#D8DEE4",
        "accent": "#6C63FF",
        "accent_tag_bg": "rgba(108,99,255,0.12)",
        "accent_tag_border": "rgba(108,99,255,0.35)",
        "accent_tag_hover": "rgba(108,99,255,0.22)",
        "card_btn_active": "rgba(108,99,255,0.08)",
        "card_faint": "rgba(0,0,0,0.03)",
        "chart_grid": "rgba(200,205,212,0.5)",
        "chart_zeroline": "rgba(200,205,212,0.7)",
        "hover_bg": "rgba(255,255,255,0.96)",
        "plotly_template": "plotly_white",
        "page_bg": "#F7F8FA",
        "range_bg": "rgba(0,0,0,0.04)",
        "range_active": "rgba(108,99,255,0.15)",
        "table_border": "#D0D7DE",
        "table_header_border": "#AFB8C1",
        "table_hover": "rgba(0,0,0,0.04)",
        "table_text": "#24292F",
        "holdings_bar_bg": "rgba(0,0,0,0.05)",
    },
}


def _detect_currency(filename: str) -> str:
    prefix = filename.strip()[:3].upper()
    return prefix if prefix in ("EUR", "PLN", "USD") else "USD"

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Negotium",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
# ── Project init ───────────────────────────────────────────────────────────────

migrated = storage.init_legacy_project()
projects = storage.list_projects()

if not projects:
    if storage.get_current_project() is None:
        storage.create_project("default")
        projects = storage.list_projects()

current = storage.get_current_project()
if current is None:
    if projects:
        storage.set_current_project(projects[0])
        current = projects[0]
    else:
        storage.create_project("default")
        current = storage.get_current_project()
        projects = storage.list_projects()

# ── Import logging ────────────────────────────────────────────────────────────

_log_dir = storage._project_dir()
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / "import.log"

_import_logger = logging.getLogger("negotium.imports")
_import_logger.setLevel(logging.DEBUG)
if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(_log_file.resolve())
           for h in _import_logger.handlers):
    _fh = logging.FileHandler(str(_log_file), encoding="utf-8")
    _fh.setLevel(logging.DEBUG)
    _fh.setFormatter(logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s"))
    _import_logger.addHandler(_fh)
    _import_logger.propagate = False

    # Route import-module loggers to the same file
    for mod_name in ("xtb_import", "bossa_import", "manual_import"):
        _child = logging.getLogger(mod_name)
        _child.setLevel(logging.DEBUG)
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(_log_file.resolve())
                   for h in _child.handlers):
            _child.addHandler(_fh)
            _child.propagate = False

# ── Config ────────────────────────────────────────────────────────────────────

cfg            = cfg_module.load()
start_date_cfg = cfg_module.get_start_date(cfg)
today          = date.today()
precision      = "D"

if "theme" not in st.session_state:
    st.session_state["theme"] = cfg_module.get_theme(cfg)
T = THEMES[st.session_state["theme"]]


st.markdown(f"""
<style>
    html, body, [class*="css"] {{ font-size: 18px !important; }}

    /* ── App-level backgrounds & text ──────────────────────────────────── */
    .stApp {{ background-color: {T["page_bg"]}; }}
    [data-testid="stHeader"] {{ background-color: {T["page_bg"]}; }}
    section[data-testid="stSidebar"] {{ background-color: {T["panel_bg"]}; }}
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ background-color: {T["panel_bg"]}; }}

    /* ── Override Streamlit dark-mode CSS variables ────────────────────── */
    :root, [data-theme="dark"] {{
        --background-color: {T["page_bg"]};
        --secondary-background-color: {T["panel_bg"]};
        --text-color: {T["text"]};
        --primary-color: {T["accent"]};
    }}
    /* BaseWeb / ThemedSelect overrides */
    [data-baseweb="select"] {{
        background-color: {T["card_bg"]} !important;
        color: {T["text"]} !important;
        border-color: {T["border"]} !important;
    }}
    [data-baseweb="select"] > div {{
        background-color: {T["card_bg"]} !important;
    }}
    [data-baseweb="input"] {{
        background-color: {T["card_bg"]} !important;
        color: {T["text"]} !important;
    }}
    [data-baseweb="tag"] {{
        background-color: {T["accent_tag_bg"]} !important;
        color: {T["text"]} !important;
    }}
    .stMarkdown p, .stMarkdown li, .stMarkdown span, .stMarkdown div,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
    .stMarkdown h5, .stMarkdown h6 {{ color: {T["text"]}; }}
    .stCaption p, .stCaption span {{ color: {T["text_muted"]}; }}
    h1, h2, h3, h4, h5, h6 {{ color: {T["text"]}; }}
    label, [data-baseweb="label"] {{ color: {T["text"]} !important; }}
    input, textarea, select {{ color: {T["text"]} !important; }}
    p, li, span {{ color: {T["text"]}; }}

    /* ── Text inputs & text areas ──────────────────────────────────────── */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input {{
        background: {T["card_bg"]} !important;
        color: {T["text"]} !important;
        border-color: {T["border"]} !important;
    }}
    [data-testid="stTextInput"] > div > div,
    [data-testid="stTextArea"] > div > div,
    [data-testid="stNumberInput"] > div > div {{
        background: {T["card_bg"]} !important;
        border-color: {T["border"]} !important;
    }}

    /* ── Selectboxes & multiselects ────────────────────────────────────── */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stSelectbox"] [data-baseweb="select"],
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] > div > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"],
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
        background: {T["card_bg"]} !important;
        border: 1px solid {T["border"]} !important;
        border-radius: 0.75rem !important;
        color: {T["text"]} !important;
    }}
    [data-testid="stMultiSelect"]:has([data-baseweb="select"]),
    [data-testid="stSelectbox"]:has([data-baseweb="select"]) {{
        max-width: 600px !important;
        width: 100% !important;
    }}
    [data-testid="stMultiSelect"] input,
    [data-testid="stSelectbox"] input {{
        background: {T["card_bg"]} !important;
        color: {T["text"]} !important;
    }}
    [data-testid="stMultiSelect"] [data-baseweb="tag"] {{
        background: {T["accent_tag_bg"]} !important;
        border: 1px solid {T["accent_tag_border"]} !important;
        border-radius: 0.5rem !important;
        color: {T["text"]} !important;
    }}
    [data-testid="stMultiSelect"] [data-baseweb="tag"] span {{
        color: {T["text"]} !important;
    }}
    [data-testid="stMultiSelect"] [aria-label="clear"] {{
        background: {T["accent_tag_hover"]} !important;
    }}
    /* Multiselect/select placeholder text ("Choose options").
       Streamlit's BaseWeb StyledPlaceholder renders with class "st-fh"
       (emotion-generated hash) and NO stable id. Its own rule has no !important,
       so our !important wins outright. */
    .st-fh {{
        color: {T["text"]} !important;
    }}
    [data-testid="stHorizontalBlock"]:has([data-baseweb="select"]):has([data-baseweb="multiselect"]) {{
        background: {T["card_bg"]};
        border: 1px solid {T["border"]};
        border-radius: 0.75rem;
        padding: 0.4rem 0.8rem;
        gap: 0 !important;
    }}

    /* ── BaseWeb dropdown popups (portalled outside widget) ─────────────── */
    /* Streamlit dark theme sets [data-theme="dark"] on body, portalled popups inherit it */
    [data-theme="dark"] [data-baseweb="popover"],
    [data-baseweb="popover"] {{
        background: {T["panel_bg"]} !important;
        border: 1px solid {T["border"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"],
    [data-theme="dark"] [data-baseweb="menu"] ul,
    [data-baseweb="menu"],
    [data-baseweb="menu"] ul {{
        background: {T["panel_bg"]} !important;
        border-color: {T["border"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="list"],
    [data-baseweb="list"] {{
        background: {T["panel_bg"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="list"] li,
    [data-baseweb="list"] li {{
        color: {T["text"]} !important;
        background: {T["panel_bg"]} !important;
    }}
    [data-theme="dark"] [role="option"],
    [data-theme="dark"] [role="listbox"] > div,
    [data-theme="dark"] [role="listbox"] > li,
    [role="option"],
    [role="listbox"] > div,
    [role="listbox"] > li {{
        color: {T["text"]} !important;
        background: transparent !important;
    }}
    [data-theme="dark"] [role="option"]:hover,
    [data-theme="dark"] [role="option"]:focus,
    [data-theme="dark"] [role="listbox"] > div:hover,
    [role="option"]:hover,
    [role="option"]:focus,
    [role="listbox"] > div:hover {{
        background: {T["card_bg"]} !important;
    }}
    [data-theme="dark"] [role="option"][aria-selected="true"],
    [role="option"][aria-selected="true"] {{
        background: {T["accent_tag_bg"]} !important;
    }}
    [data-theme="dark"] [role="option"] [data-baseweb="highlight"],
    [role="option"] [data-baseweb="highlight"] {{
        background: {T["accent_tag_bg"]} !important;
    }}
    /* Nuclear override: force all descendants of portalled popover */
    [data-baseweb="popover"] [data-baseweb="menu"] [role="option"] {{
        background-color: {T["panel_bg"]} !important;
        color: {T["text"]} !important;
    }}
    [data-baseweb="popover"] [data-baseweb="menu"] [role="option"]:hover {{
        background-color: {T["card_bg"]} !important;
    }}
    [data-baseweb="popover"] [data-baseweb="menu"] {{
        background-color: {T["panel_bg"]} !important;
    }}

    /* ── Metric cards ──────────────────────────────────────────────────── */
    [data-testid="metric-container"] {{
        background: {T["card_bg"]} !important;
        border: 1px solid {T["border"]} !important;
        border-radius: 16px !important;
        padding: 28px 24px 16px 24px !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricLabel"],
    [data-testid="metric-container"] [data-testid="stMetricLabel"] p,
    [data-testid="metric-container"] label,
    [data-testid="metric-container"] label p,
    [data-testid="metric-container"] [class*="Label"],
    [data-testid="metric-container"] [class*="Label"] p {{
        color: {T["text_muted"]} !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        visibility: visible !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricValue"],
    [data-testid="metric-container"] [class*="Value"],
    [data-testid="metric-container"] [class*="Value"] p {{
        font-size: 2rem !important;
        font-weight: 700 !important;
        color: {T["text"]} !important;
    }}

    /* ── Sidebar ───────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {{
        min-width: 380px;
        max-width: 420px;
        border-right: 1px solid {T["border_strong"]};
    }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {{ margin-top: -0.4rem; }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:first-child {{ margin-top: 0; }}
    [data-testid="stSidebar"] hr {{ display: none; }}
    [data-testid="stSidebar"] button[kind="primary"] {{
        background: {T["card_bg"]} !important;
        border: 1px solid {T["border"]} !important;
    }}
    [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {{ gap: 0.3rem; }}
    [data-testid="stSidebar"] [data-testid="stMarkdown"] h1 {{
        font-size: 2rem !important;
        text-align: center !important;
        margin-top: -1rem !important;
        padding-top: 0 !important;
    }}
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-baseweb="label"] {{
        color: {T["text_muted"]} !important;
    }}
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div {{
        color: {T["text"]};
    }}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
        color: {T["text_muted"]};
    }}

    /* ── Main content spacing ──────────────────────────────────────────── */
    .block-container {{
        padding-top: 2.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }}

    /* ── Expanders ─────────────────────────────────────────────────────── */
    details[data-testid="stExpander"] {{
        background: {T["panel_bg"]} !important;
        background-color: {T["panel_bg"]} !important;
        border: 1px solid {T["border_strong"]} !important;
        border-radius: 12px !important;
        --secondary-background-color: {T["panel_bg"]};
    }}
    details[data-testid="stExpander"] summary,
    details[data-testid="stExpander"] summary span,
    details[data-testid="stExpander"] summary p {{
        color: {T["text"]} !important;
        background: transparent !important;
        background-color: transparent !important;
        --secondary-background-color: {T["panel_bg"]};
    }}
    details[data-testid="stExpander"]:hover,
    details[data-testid="stExpander"][open] {{
        background: {T["panel_bg"]} !important;
        border-color: {T["border_strong"]} !important;
    }}
    details[data-testid="stExpander"] summary:hover,
    details[data-testid="stExpander"] summary:focus,
    details[data-testid="stExpander"] summary:active {{
        background: {T["card_bg"]} !important;
        color: {T["text"]} !important;
        outline: none !important;
        border-color: transparent !important;
    }}

    /* ── Buttons (global) ──────────────────────────────────────────────── */
    .stButton > button,
    .stDownloadButton > button,
    div[data-testid="stHorizontalBlock"] button {{
        background: {T["card_bg"]} !important;
        border: 1px solid {T["border"]} !important;
        border-radius: 0.75rem !important;
        color: {T["text"]} !important;
    }}
    .stButton > button:hover,
    .stDownloadButton > button:hover,
    div[data-testid="stHorizontalBlock"] button:hover {{
        border-color: {T["border_hover"]} !important;
    }}

    /* ── Dividers ──────────────────────────────────────────────────────── */
    hr {{ border-color: {T["hr"]} !important; }}

    /* ── Plotly chart card ─────────────────────────────────────────────── */
    [data-testid="stPlotlyChart"] {{
        background: {T["card_bg"]};
        border-radius: 1rem;
        padding: 0.1rem;
        margin: 0.5rem 0 0 0;
    }}

    /* ── DataFrame ─────────────────────────────────────────────────────── */
    [data-testid="stDataFrame"] {{
        border: 1px solid {T["border_strong"]};
        border-radius: 12px;
        overflow: hidden;
    }}

    /* ── Info / Warning / Error / Success boxes ────────────────────────── */
    [data-testid="stAlert"] {{
        background: {T["card_bg"]} !important;
        color: {T["text"]} !important;
        border-color: {T["border"]} !important;
    }}

    /* ── Tabs ──────────────────────────────────────────────────────────── */
    [data-baseweb="tab-list"] {{ background: {T["panel_bg"]} !important; }}
    [data-baseweb="tab"] {{ color: {T["text_muted"]} !important; }}
    [data-baseweb="tab"][aria-selected="true"] {{ color: {T["text"]} !important; }}
    [data-baseweb="tab-border"] {{ border-color: {T["border"]} !important; }}
    [data-baseweb="tab-highlight"] {{ background-color: {T["accent"]} !important; }}

    /* ── Code blocks ───────────────────────────────────────────────────── */
    code {{ color: {T["text"]} !important; background: {T["card_bg"]} !important; }}
    pre {{ background: {T["card_bg"]} !important; border: 1px solid {T["border"]} !important; }}
    pre code {{ color: {T["text_cell"]} !important; }}

    /* ── Checkboxes & radio buttons ────────────────────────────────────── */
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] label {{
        color: {T["text"]} !important;
    }}

    /* ── Date input dropdowns ──────────────────────────────────────────── */
    [data-testid="stDateInput"] [data-baseweb="input"] {{
        background: {T["card_bg"]} !important;
        color: {T["text"]} !important;
    }}

    /* ── Form submit buttons ───────────────────────────────────────────── */
    .stFormSubmitButton > button {{
        background: {T["accent"]} !important;
        color: #fff !important;
        border: none !important;
    }}
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(f"""
    <style>
    [data-testid="stSidebar"] .stSelectbox > div > div,
    [data-testid="stSidebar"] .stRadio > div,
    [data-testid="stSidebar"] [data-testid="stExpander"] {{
        background: {T["card_bg"]} !important;
        border: 1px solid {T["border"]} !important;
        border-radius: 0.75rem !important;
    }}
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {{
        padding: 0.6rem 0.8rem !important;
    }}
    [data-testid="stSidebar"] .stButton > button {{
        background: {T["card_bg"]} !important;
        border: 1px solid {T["border"]} !important;
        border-radius: 0.75rem !important;
        color: {T["text"]} !important;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{
        border-color: {T["border_hover"]} !important;
    }}
    [data-testid="stSidebar"] label {{
        color: {T["text_muted"]} !important;
    }}
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span {{
        color: {T["text"]};
    }}
    [data-testid="stSidebar"] [data-testid="stTextInput"] input,
    [data-testid="stSidebar"] [data-testid="stTextArea"] textarea,
    [data-testid="stSidebar"] [data-testid="stNumberInput"] input {{
        background: {T["card_bg"]} !important;
        color: {T["text"]} !important;
        border-color: {T["border"]} !important;
    }}
    [data-testid="stSidebar"] [data-testid="stTextInput"] > div > div,
    [data-testid="stSidebar"] [data-testid="stTextArea"] > div > div,
    [data-testid="stSidebar"] [data-testid="stNumberInput"] > div > div {{
        background: {T["card_bg"]} !important;
        border-color: {T["border"]} !important;
    }}
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {{
        font-size: 0.8rem !important;
        color: {T["text_muted"]} !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        margin-top: 0.8rem !important;
    }}
    </style>
    """, unsafe_allow_html=True)
    project_name = html.escape(storage.get_current_project())
    st.markdown(
        f"""<div style="
            padding:0.8rem 1.2rem; border-radius:0.75rem; text-align:center;
            background:{T["card_bg"]}; border:1px solid {T["border"]};
            margin-top:-1rem; margin-bottom:0.5rem;
        ">
            <div style="font-size:1.6rem; font-weight:700; color:{T["text"]};">📈 {project_name}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Project switcher ───────────────────────────────────────────────────
    projects = storage.list_projects()
    current = storage.get_current_project()

    if current and current in projects:
        idx = projects.index(current)
    else:
        idx = 0

    selected = st.selectbox(
        "Project",
        options=projects + ["➕ New project"],
        index=idx,
        key="project_select",
    )

    if selected == "➕ New project":
        @st.dialog("Create new project")
        def _create_dialog():
            name = st.text_input("Project name", placeholder="e.g. Retirement, Savings")
            if st.button("Create", use_container_width=True):
                if name and name.strip():
                    try:
                        storage.create_project(name.strip())
                        st.session_state.clear()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                else:
                    st.error("Enter a name.")
        _create_dialog()
    elif selected != current:
        storage.set_current_project(selected)
        st.session_state.clear()
        st.rerun()

    # ── Display controls ───────────────────────────────────────────────────
    st.caption("Currency")
    ccy_options = ["PLN", "EUR", "USD"]
    ccy_default = ccy_options.index(cfg.get("default_currency", "PLN"))
    ccy_cols = st.columns(3)
    base_ccy = None
    for i, ccy in enumerate(ccy_options):
        with ccy_cols[i]:
            is_active = st.session_state.get("base_ccy_idx", ccy_default) == i
            if st.button(
                ccy,
                key=f"ccy_btn_{ccy}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state["base_ccy_idx"] = i
                base_ccy = ccy
                st.rerun()
    if base_ccy is None:
        base_ccy = ccy_options[st.session_state.get("base_ccy_idx", ccy_default)]

    _range_opts = ["All time", "This year", "Last 12 months", "Last 3 months", "Custom"]
    if "_range" not in st.session_state:
        st.session_state["_range"] = "All time"

    def _on_range_change():
        st.session_state["_range"] = st.session_state["range_widget"]

    range_option = st.session_state["_range"]
    if range_option == "All time":
        chart_start, chart_end = start_date_cfg, today
    elif range_option == "This year":
        chart_start, chart_end = date(today.year, 1, 1), today
    elif range_option == "Last 12 months":
        chart_start, chart_end = today - timedelta(days=365), today
    elif range_option == "Last 3 months":
        chart_start, chart_end = today - timedelta(days=90), today
    else:
        ca, cb = st.columns(2)
        with ca:
            chart_start = st.date_input("From", value=start_date_cfg,
                                        min_value=start_date_cfg, max_value=today,
                                        key="range_from")
        with cb:
            chart_end = st.date_input("To", value=today,
                                      min_value=start_date_cfg, max_value=today,
                                      key="range_to")

    with st.expander("⚙️ Settings"):
        st.subheader("Appearance")
        current_theme = st.session_state.get("theme", "dark")
        light_on = st.toggle(
            "Light mode",
            value=(current_theme == "light"),
            key="theme_toggle",
        )
        new_theme = "light" if light_on else "dark"
        if new_theme != current_theme:
            st.session_state["theme"] = new_theme
            cfg_module.save_theme(new_theme)
            st.rerun()

        st.subheader("Ticker rules")
        rules_text = st.text_area(
            "Rules",
            value="\n".join(cfg.get("ticker_rules", [])),
            height=200,
            key="ticker_rules_text",
            label_visibility="collapsed",
            placeholder="AMZN.DE=AMZ.DE\n*.PL=*.WA\n.US=",
        )
        if st.button("Save ticker rules"):
            new_rules = [line.strip() for line in rules_text.strip().splitlines() if line.strip()]
            cfg["ticker_rules"] = new_rules
            cfg_module.save(cfg)
            st.success("Rules saved!")
            st.rerun()

        st.subheader("Project")

        rename_val = st.text_input("Rename project to", value=current or "",
                                   key="rename_proj_input")
        if st.button("Rename", key="rename_proj_btn"):
            if rename_val and rename_val.strip() and rename_val.strip() != current:
                try:
                    storage.rename_project(current, rename_val.strip())
                    st.session_state.clear()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    with st.expander("➕ Add transaction"):
        with st.form("add_tx", clear_on_submit=True):
            tx_date = st.date_input("Date", value=today, max_value=today)
            st.caption("Negative amount = sell / cash out.")

            rows = []
            for idx in range(1, 3):
                c1, c2 = st.columns([2, 1])
                with c1:
                    t = st.text_input(
                        f"Ticker {idx}",
                        placeholder="AAPL / QDVE.DE / USD / PLN",
                        key=f"t{idx}",
                    ).strip().upper()
                with c2:
                    a = st.number_input(f"Amount {idx}", value=0.0,
                                        format="%.4f", step=0.001, key=f"a{idx}")
                rows.append((t, a))

            is_account_op = st.checkbox("Account operation (deposit/withdrawal)",
                                        key="ao_new",
                                        help="Marks this transaction as invested capital")

            if st.form_submit_button("Add transaction", width="stretch"):
                entries = [{"ticker": t, "amount": a,
                            **({"account_operation": True} if is_account_op else {})}
                           for t, a in rows if t and abs(a) > 1e-9]
                if not entries:
                    st.error("Enter at least one ticker and amount.")
                else:
                    custom_dir = storage.IMPORTS_DIR / "custom"
                    custom_dir.mkdir(parents=True, exist_ok=True)
                    tx_doc = [{"date": tx_date.isoformat(), "entries": entries}]
                    tx_path = custom_dir / f"{tx_date.isoformat()}_{datetime.now().strftime('%H%M%S')}.json"
                    tx_path.write_text(json.dumps(tx_doc, indent=2), encoding="utf-8")
                    result = import_manual(str(tx_path))
                    if result["success"]:
                        st.success(f"Added for {tx_date}.")
                    else:
                        st.error(result["error"])
                    st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
                    st.rerun()

    with st.expander("📥 Import statement"):
        storage.IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

        broker = st.selectbox("Broker", BROKERS, key="broker_select")
        broker_dir = storage.IMPORTS_DIR / broker.lower()
        broker_dir.mkdir(parents=True, exist_ok=True)

        if broker == "XTB":
            st.info("ℹ️ Name your file starting with the currency code, e.g. `EUR_history.xlsx` — the currency is auto-detected from the prefix.")

        file_types = ["csv"] if broker == "BOSSA" else ["json"] if broker == "Custom" else ["xlsx"]
        uploaded_files = st.file_uploader(
            f"Upload {broker} files", type=file_types,
            accept_multiple_files=True, key=f"{broker}_upload",
            label_visibility="collapsed",
        )

        if uploaded_files:
            for uf in uploaded_files:
                dest = broker_dir / uf.name
                dest.write_bytes(uf.getvalue())
                detected = _detect_currency(uf.name)
                if broker == "BOSSA":
                    ccy = "Many"
                    with st.spinner(f"Importing {uf.name}…"):
                        result = import_bossa(str(dest), ccy)
                elif broker == "Custom":
                    with st.spinner(f"Importing {uf.name}…"):
                        result = import_manual(str(dest))
                else:
                    ccy_options = BROKER_CURRENCIES.get(broker, ["EUR", "PLN", "USD"])
                    if detected not in ccy_options:
                        detected = ccy_options[0]
                    with st.spinner(f"Importing {uf.name}…"):
                        result = import_xtb(str(dest), detected)
                if result["success"]:
                    n = result["imported"]
                    s = result["skipped"]
                    msg = f"**{uf.name}** — {n} imported"
                    if s:
                        msg += f", {s} skipped (duplicates)"
                    st.success(msg)
                else:
                    st.error(f"**{uf.name}** — {result['error']}")
            st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
            st.rerun()

        broker_files = sorted(broker_dir.glob("*.xlsx")) + sorted(broker_dir.glob("*.csv")) + sorted(broker_dir.glob("*.json"))
        if broker_files:
            for fpath in broker_files:
                st.caption(f"📄 {fpath.name}")
        else:
            st.caption("No files uploaded yet.")

    if st.button("📈  Refresh market data", width="stretch"):
        all_files = []
        for b in BROKERS:
            bdir = storage.IMPORTS_DIR / b.lower()
            if not bdir.exists():
                continue
            for fpath in sorted(bdir.glob("*.xlsx")):
                all_files.append(("xtb", fpath))
            for fpath in sorted(bdir.glob("*.csv")):
                all_files.append(("bossa", fpath))
            for fpath in sorted(bdir.glob("*.json")):
                all_files.append(("custom", fpath))

        if all_files:
            bar = st.progress(0, text="Importing…")
            total_imported = 0
            for idx, (kind, fpath) in enumerate(all_files):
                ccy = _detect_currency(fpath.name)
                bar.progress(idx / len(all_files), text=f"Importing {fpath.name}…")
                if kind == "bossa":
                    result = import_bossa(str(fpath), ccy)
                elif kind == "custom":
                    result = import_manual(str(fpath))
                else:
                    result = import_xtb(str(fpath), ccy)
                if result["success"]:
                    total_imported += result["imported"]
            bar.progress(1.0, text="Done")
            bar.empty()
            st.success(f"Refreshed from {len(all_files)} files — {total_imported} transactions imported.")
        else:
            st.info("No import files found.")

        storage.invalidate_portfolio_from((today - timedelta(days=1)).isoformat())
        st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
        for k in list(st.session_state.keys()):
            if k.startswith("benchmarks_"):
                st.session_state.pop(k)
        st.session_state["force_refresh"] = True
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

all_tx = get_all_transactions()
if not all_tx:
    st.markdown(f"""
    <div style="text-align:center;padding:4rem 2rem;border-radius:1rem;background:{T["card_bg"]};border:1px solid {T["border"]};margin:2rem 0;">
        <div style="font-size:3rem;margin-bottom:1rem;">📈</div>
        <div style="font-size:1.4rem;font-weight:600;color:{T["text"]};margin-bottom:0.5rem;">No transactions yet</div>
        <div style="font-size:1rem;color:{T["text_muted"]};margin-bottom:0.3rem;">Add your first one using the sidebar form.</div>
        <div style="font-size:0.85rem;color:{T["text_muted"]};">Example: Ticker 1 = <code style="color:{T["accent"]};">AAPL</code>, Amount 1 = <code style="color:{T["accent"]};">10</code> / Ticker 2 = <code style="color:{T["accent"]};">USD</code>, Amount 2 = <code style="color:{T["accent"]};">-1700</code></div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Market data download ──────────────────────────────────────────────────────

tickers_needed = get_all_tickers(include_fx=True)
force_refresh  = st.session_state.pop("force_refresh", False)

# Check which tickers actually need downloading
missing = [
    t for t in tickers_needed
    if t not in storage.SUPPORTED_CURRENCIES
    and (force_refresh or not storage.has_price_year(t, today.year))
]

download_errors: list[str] = []

if missing:
    dl_bar = st.progress(0, text=f"Downloading {len(missing)} tickers…")

    try:
        download_errors = ensure_batch(
            missing,
            start_date=start_date_cfg,
            force_refresh_current_year=True,
            progress_cb=lambda msg: dl_bar.progress(0, text=msg),
        )
    except Exception as e:
        download_errors = list(missing)
        st.caption(f"⚠ Batch download failed: {e}")

    dl_bar.empty()

    if download_errors:
        st.warning(
            f"⚠️ Could not download price data for: **{', '.join(download_errors)}**\n\n"
            "These positions will be missing from the chart. "
            "Check your internet connection and try **Refresh market data**."
        )

# ── Rebuild balance after price refresh (fixes stale avg_price) ──────────────

if force_refresh:
    rebuild_balance()

# Warn if we have stock tickers but zero price files at all
stock_tickers = [t for t in tickers_needed
                 if t not in storage.SUPPORTED_CURRENCIES and t not in FX_TICKERS]
tickers_with_data = [t for t in stock_tickers if storage.has_price_year(t, today.year)
                     or any(storage.has_price_year(t, y) for y in range(start_date_cfg.year, today.year + 1))]
tickers_without_data = [t for t in stock_tickers if t not in tickers_with_data]

if tickers_without_data:
    st.error(
        f"❌ No price data available for: **{', '.join(tickers_without_data)}**\n\n"
        "These tickers will not appear in the chart. "
        "Make sure you're connected to the internet and the ticker symbols are correct "
        "(e.g. `QDVE.DE` for Xetra, `CDR.WA` for Warsaw, `AAPL` for NASDAQ)."
    )

# ── Build portfolio ───────────────────────────────────────────────────────────

cache_key = f"snapshots_{base_ccy}_{precision}"

if cache_key not in st.session_state:
    bar = st.progress(0, text="Building portfolio…")

    def _on_progress(day_str: str, pct: float):
        bar.progress(min(pct, 1.0), text=f"Computing {day_str}…")

    t_start = time.perf_counter()
    all_snapshots = build_portfolio(
        start_date=start_date_cfg,
        end_date=today,
        base_currency=base_ccy,
        precision=precision,
        progress_cb=_on_progress,
        use_cache=True,
    )
    elapsed = time.perf_counter() - t_start
    bar.empty()

    log_path = storage._project_dir() / "build.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{today.isoformat()} {time.strftime('%H:%M:%S')} | "
                f"{base_ccy} {precision} | {elapsed:.3f}s | "
                f"{len(all_snapshots)} snapshots\n")

    st.session_state[cache_key] = all_snapshots

all_snapshots: list[dict] = st.session_state[cache_key]

BENCHMARKS = {
    "NASDAQ 100 (SXRV.DE)": "SXRV.DE",
    "S&P 500 (I500.DE)": "I500.DE",
    "Vanguard FTSE All-World (VWCE.DE)": "VWCE.DE",
    "Emerging Markets (IS3N.DE)": "IS3N.DE",
    "Bitcoin (BTCE.DE)": "BTCE.DE",
    "Gold (4GLD.DE)": "4GLD.DE",
}
BENCH_COLORS = {
    "NASDAQ 100 (SXRV.DE)": "#06b6d4",
    "S&P 500 (I500.DE)": "#22c55e",
    "Vanguard FTSE All-World (VWCE.DE)": "#f97316",
    "Emerging Markets (IS3N.DE)": "#8b5cf6",
    "Bitcoin (BTCE.DE)": "#ef4444",
    "Gold (4GLD.DE)": "#eab308",
}

# ── Download data for selected benchmarks ─────────────────────────────────────
bench_persist = st.session_state.get("bench_persist", [])
if bench_persist:
    bench_date_start = date.fromisoformat(all_snapshots[0]["date"])
    bench_date_end = date.fromisoformat(all_snapshots[-1]["date"])
    bench_tickers_needed = [BENCHMARKS[k] for k in bench_persist if k in BENCHMARKS]
    bench_missing = [
        t for t in bench_tickers_needed
        if t not in storage.SUPPORTED_CURRENCIES
        and (force_refresh or not storage.has_price_year(t, today.year))
    ]
    if bench_missing:
        bench_dl = st.progress(0, text="Downloading benchmark data…")
        try:
            ensure_batch(bench_missing, bench_date_start, bench_date_end,
                         force_refresh_current_year=force_refresh,
                         progress_cb=lambda msg: bench_dl.progress(0, text=msg))
        except Exception as e:
            st.warning(f"Could not download benchmarks: {e}")
        bench_dl.progress(1.0, text="Done")
        bench_dl.empty()
        # Clear benchmark cache so new data is used
        for k in list(st.session_state.keys()):
            if k.startswith("benchmarks_"):
                del st.session_state[k]

# ── Compute & cache benchmarks ────────────────────────────────────────────────

bench_cache_key = f"benchmarks_{base_ccy}_{len(all_snapshots)}_{len(BENCHMARKS)}"
if bench_cache_key not in st.session_state:
    cached = storage.load_benchmarks(base_ccy) if not force_refresh else None
    if (cached and len(cached) == len(all_snapshots)
            and all(k in cached[0] for k in BENCHMARKS.values())):
        st.session_state[bench_cache_key] = cached
    else:
        bench_date_start = date.fromisoformat(all_snapshots[0]["date"])
        bench_date_end = date.fromisoformat(all_snapshots[-1]["date"])
        bench_result: list[dict] = []
        bench_tickers = [b_ticker for b_ticker in BENCHMARKS.values()
                         if any(not storage.has_price_year(b_ticker, y)
                                or (force_refresh and y == today.year)
                                for y in range(bench_date_start.year, bench_date_end.year + 1))]
        if bench_tickers:
            ensure_batch(bench_tickers, bench_date_start, bench_date_end,
                         force_refresh_current_year=force_refresh)

        for b_label, b_ticker in BENCHMARKS.items():
            if not any(storage.has_price_year(b_ticker, y)
                       for y in range(bench_date_start.year, bench_date_end.year + 1)):
                continue

            fx_c: dict = {}
            bp_c: dict = {}
            b_vals: list[float] = []
            cum_units = 0.0
            prev_inv = 0.0

            for snap in all_snapshots:
                day = snap["date"]
                yr = int(day[:4])
                new_inv = snap["invested"] - prev_inv
                prev_inv = snap["invested"]

                price = get_price(b_ticker, day, bp_c, yr)
                if price is None or price <= 0:
                    b_vals.append(b_vals[-1] if b_vals else 0.0)
                    continue

                if base_ccy == "EUR":
                    new_eur = new_inv
                else:
                    fx_to_eur = get_fx_rate(base_ccy, "EUR", day, fx_c, yr)
                    new_eur = new_inv * fx_to_eur

                cum_units += new_eur / price

                if base_ccy == "EUR":
                    hyp = cum_units * price
                else:
                    fx_to_base = get_fx_rate("EUR", base_ccy, day, fx_c, yr)
                    hyp = cum_units * price * fx_to_base

                b_vals.append(round(hyp, 2))

            if not bench_result:
                bench_result = [{"date": s["date"]} for s in all_snapshots]
            for i, v in enumerate(b_vals):
                bench_result[i][b_ticker] = v

        storage.save_benchmarks(base_ccy, bench_result)
        st.session_state[bench_cache_key] = bench_result

all_benchmarks: list[dict] = st.session_state.get(bench_cache_key, [])

# ── Bench index by date ──────────────────────────────────────────────────────
bench_by_date: dict[str, dict] = {b["date"]: b for b in all_benchmarks}

# Filter to chart date range
cs = chart_start.isoformat()
ce = chart_end.isoformat()
snapshots = [s for s in all_snapshots if cs <= s["date"] <= ce]

# Filter out leading zero-value snapshots (before first transaction)
first_nonzero = next((i for i, s in enumerate(snapshots) if s["total_value"] != 0.0), None)
if first_nonzero is not None:
    snapshots = snapshots[first_nonzero:]

if not snapshots:
    st.warning("No portfolio data for the selected date range. Try 'All time' or add transactions.")
    st.stop()

dates, values, investeds = snapshots_to_series(snapshots)

# ── Metric cards ──────────────────────────────────────────────────────────────

latest = snapshots[-1]
prev   = snapshots[-2] if len(snapshots) > 1 else None

cur_value  = latest["total_value"]
contrib    = latest["invested"]
pnl        = cur_value - contrib
pnl_pct    = (pnl / contrib * 100) if contrib else 0.0
day_change = (cur_value - prev["total_value"]) if prev else 0.0
day_pct    = (day_change / prev["total_value"] * 100) if prev and prev["total_value"] else 0.0

SYM = {"PLN": " PLN", "EUR": "€", "USD": "$"}

def fmt(v: float) -> str:
    formatted = f"{v:,.0f}".replace(",", " ")
    if base_ccy == "PLN":
        return f"{formatted} PLN"
    return f"{SYM[base_ccy]}{formatted}"

cagr = compute_cagr(cur_value, base_ccy)
irr = compute_irr(cur_value, base_ccy)

best_ticker = max(latest["assets"], key=lambda a: a["value_base"])["ticker"] if latest["assets"] else "—"

cagr_str = f"{cagr * 100:.1f}%" if cagr is not None else "—"
irr_str = f"{irr * 100:.1f}%" if irr is not None else "—"

st.markdown(f"""
<style>
.stat-row {{ display:flex; gap:1rem; margin:0.5rem 0 1rem 0; }}
.stat-card {{
  flex:1; padding:0.8rem 1.2rem; border-radius:0.75rem;
  background:{T["card_bg"]};
  border:1px solid {T["border"]};
}}
.stat-card .label {{ font-size:0.75rem; color:{T["text_faint"]}; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.2rem; text-align:center; }}
.stat-card .value {{ font-size:1.4rem; font-weight:700; color:{T["text"]}; text-align:center; }}
.green .value,
.blue .value,
.purple .value,
.amber .value,
.cyan .value {{ color:{T["text"]}; }}
</style>
<div class="stat-row">
  <div class="stat-card cyan" title="Current market value of all holdings in {base_ccy}">
    <div class="label">Total Value</div>
    <div class="value">{fmt(cur_value)}</div>
  </div>
  <div class="stat-card blue" title="Net deposits minus withdrawals across all accounts">
    <div class="label">Invested</div>
    <div class="value">{fmt(contrib)}</div>
  </div>
  <div class="stat-card purple" title="The position with the highest current value">
    <div class="label">Largest Position</div>
    <div class="value">{best_ticker}</div>
  </div>
  <div class="stat-card green" title="Compound Annual Growth Rate — smoothed yearly return since first deposit">
    <div class="label">CAGR</div>
    <div class="value">{cagr_str}</div>
  </div>
  <div class="stat-card amber" title="Internal Rate of Return — accounts for exact timing of every deposit">
    <div class="label">IRR</div>
    <div class="value">{irr_str}</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── P&L toggle blocks ────────────────────────────────────────────────────────

if "chart_mode" not in st.session_state:
    st.session_state.chart_mode = "amount"

sign = "+" if pnl >= 0 else ""
is_amount = st.session_state.chart_mode == "amount"
is_percent = not is_amount

st.markdown(f"""
<style>
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="secondary"]) button[kind="secondary"],
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="primary"]) button[kind="primary"] {{
        background: {T["card_bg"]} !important;
        border: 1px solid {T["border"]} !important;
        border-radius: 16px !important;
        padding: 20px 24px !important;
        min-height: 85px !important;
        width: 100% !important;
        transition: all 0.2s ease !important;
        color: {T["text"]} !important;
        font-size: 1.7rem !important;
        font-weight: 600 !important;
    }}
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="secondary"]) button[kind="secondary"]:hover,
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="primary"]) button[kind="primary"]:hover {{
        border-color: {T["border_hover"]} !important;
    }}
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="primary"]) button[kind="primary"] {{
        border-color: {T["border_active"]} !important;
        background: {T["card_btn_active"]} !important;
    }}
    div[data-testid="stHorizontalBlock"] button p {{
        font-size: 1.4rem !important;
        font-weight: 600 !important;
    }}
</style>
""", unsafe_allow_html=True)

pln_col1, pln_col2 = st.columns(2)

with pln_col1:
    if st.button(
        f"Total P&L  ·  {sign}{fmt(pnl)}",
        key="pnl_amount_btn",
        type="primary" if is_amount else "secondary",
        use_container_width=True,
    ):
        st.session_state.chart_mode = "amount"
        st.rerun()

with pln_col2:
    if st.button(
        f"Total Return  ·  {sign}{pnl_pct:.1f}%",
        key="pnl_pct_btn",
        type="primary" if is_percent else "secondary",
        use_container_width=True,
    ):
        st.session_state.chart_mode = "percent"
        st.rerun()


# ── Chart ─────────────────────────────────────────────────────────────────────

chart_mode = st.session_state.chart_mode

fig = go.Figure()

if chart_mode == "amount":
    fig.add_trace(go.Scatter(
        x=dates, y=[round(v, 2) for v in values],
        name=f"Portfolio ({base_ccy})",
        fill="tozeroy",
        line=dict(color="#6C63FF", width=2.5),
        fillcolor="rgba(108,99,255,0.08)",
        customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in values],
        hovertemplate="%{customdata}<extra>Portfolio</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=[round(v, 2) for v in investeds],
        name="Invested",
        line=dict(color="#94a3b8", width=1.5, dash="dot"),
        customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in investeds],
        hovertemplate="%{customdata}<extra>Invested</extra>",
    ))
    yaxis_cfg = dict(
        showgrid=True, gridcolor=T["chart_grid"],
        zeroline=False, tickfont=dict(size=20, color=T["text_muted"]), tickformat=",.2f",
        ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
        tickprefix="" if base_ccy == "PLN" else SYM[base_ccy],
        title=dict(font=dict(size=18, color=T["text_muted"]))
    )
else:
    pct_values = []
    for v, inv in zip(values, investeds):
        pct_values.append(round(((v / inv) - 1.0) * 100.0, 2) if inv else 0.0)
    fig.add_trace(go.Scatter(
        x=dates, y=pct_values,
        name="Return (%)",
        fill="tozeroy",
        line=dict(color="#6C63FF", width=2.5),
        fillcolor="rgba(108,99,255,0.08)",
        hovertemplate="%{y:+.2f}%<extra>Return</extra>",
    ))
    span = max(abs(min(pct_values)), abs(max(pct_values))) if pct_values else 1
    yaxis_cfg = dict(
        showgrid=True, gridcolor=T["chart_grid"],
        zeroline=True, zerolinecolor=T["chart_zeroline"],
        tickfont=dict(size=20, color=T["text_muted"]),
        ticksuffix="%",
        tickformat="+.1f",
        title=dict(font=dict(size=18, color=T["text_muted"]))
    )

bench_selected = {
    label: label in st.session_state.get("bench_persist", [])
    for label in BENCHMARKS
}

for bench_label, bench_ticker in BENCHMARKS.items():
    if not bench_selected.get(bench_label):
        continue

    bench_vals = [bench_by_date.get(d, {}).get(bench_ticker, 0.0) for d in dates]
    if chart_mode == "percent":
        bench_pcts = [
            round(((bv / inv) - 1.0) * 100.0, 2) if inv else 0.0
            for bv, inv in zip(bench_vals, investeds)
        ]
        fig.add_trace(go.Scatter(
            x=dates, y=bench_pcts,
            name=bench_label,
            line=dict(color=BENCH_COLORS[bench_label], width=1.5, dash="dot"),
            hovertemplate="%{y:+.2f}%<extra>" + bench_label + "</extra>",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=dates, y=bench_vals,
            name=bench_label,
            line=dict(color=BENCH_COLORS[bench_label], width=1.5, dash="dot"),
            customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in bench_vals],
            hovertemplate="%{customdata}<extra>" + bench_label + "</extra>",
        ))

if chart_mode == "amount":
    ys = [v for tr in fig.data if tr.y is not None for v in tr.y if v is not None]
    if ys:
        lo, hi = min(ys), max(ys)
        pad = (hi - lo) * 0.05 or 1.0
        yaxis_cfg["range"] = [lo - pad, hi + pad]

fig.update_layout(
    height=700,
    margin=dict(l=0, r=0, t=40, b=70),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
            font=dict(size=14, color=T["text_muted"]),
            bgcolor="rgba(0,0,0,0)",
        ),
    xaxis=dict(
        showgrid=False, zeroline=False,
        tickfont=dict(size=20, color=T["text_muted"]),
        title=dict(font=dict(size=18, color=T["text_muted"]))
    ),
    yaxis=yaxis_cfg,
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor=T["hover_bg"],
        bordercolor=T["border_strong"],
        font=dict(size=18, color=T["text"], family="sans-serif"),
        namelength=-1,
    ),
    font=dict(family="sans-serif", size=20),
)
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

_bench_col, _range_col = st.columns([1, 1], vertical_alignment="center", gap="xxsmall")
with _bench_col:
    bench_selected_keys = st.multiselect(
        "What-if benchmarks",
        options=list(BENCHMARKS.keys()),
        key="bench_select",
        on_change=lambda: st.session_state.update(bench_persist=list(st.session_state.bench_select)),
    )
with _range_col:
    st.selectbox(
        "Range",
        _range_opts,
        key="range_widget",
        index=_range_opts.index(st.session_state["_range"]),
        on_change=_on_range_change,
    )

# ── Trade-history dialog ────────────────────────────────────────────────────────

@st.dialog("Trade history", width="large")
def _show_trade_dialog(ticker: str, name: str, ccy: str):
    st.subheader(f"{name} ({ticker})")

    st.markdown(f"""
    <style>
    [role="dialog"],
    [data-testid="stDialog"] {{ min-width:95vw !important; min-height:85vh !important; max-width:95vw !important; background-color:{T["panel_bg"]} !important; border:1px solid {T["border_strong"]} !important; }}
    [role="dialog"] > div,
    [data-testid="stDialog"] > div {{ width:100% !important; max-width:100% !important; height:100% !important; background-color:{T["panel_bg"]} !important; border:1px solid {T["border_strong"]} !important; }}
    [role="dialog"] [data-testid="stVerticalBlock"],
    [data-testid="stDialog"] [data-testid="stVerticalBlock"] {{ background-color:{T["panel_bg"]} !important; }}
    [data-testid="stDialog"] .stMetric label {{ font-size:3rem !important; }}
    [data-testid="stDialog"] .stMetric [data-testid="stMetricValue"] {{ font-size:3rem !important; }}
    [data-testid="stDialog"] h3 {{ font-size:1.5rem !important; font-weight:600 !important; color:{T["text_muted"]} !important; }}
    [role="dialog"] button[aria-label="Close"],
    [data-testid="stDialog"] button[aria-label="Close"] {{ color:{T["text"]} !important; background-color:transparent !important; }}
    [role="dialog"] button[aria-label="Close"]:hover,
    [data-testid="stDialog"] button[aria-label="Close"]:hover {{ background-color:{T["card_bg"]} !important; }}
    </style>
    """, unsafe_allow_html=True)

    history = get_ticker_history(ticker)
    if not history:
        st.markdown(f"""
        <div style="text-align:center;padding:3rem 2rem;border-radius:1rem;background:{T["card_bg"]};border:1px solid {T["border"]};margin:1rem 0;">
            <div style="font-size:1.2rem;font-weight:600;color:{T["text"]};margin-bottom:0.3rem;">No trades found</div>
            <div style="font-size:0.9rem;color:{T["text_muted"]};">This position has no trade history yet.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    current_price = get_price(ticker, today.isoformat(), {}, today.year)

    price_cache: dict = {}
    fx_cache: dict = {}
    enriched = []
    for trade in history:
        yr = int(trade["date"][:4])
        price = get_price(ticker, trade["date"], price_cache, yr)
        if ccy != base_ccy:
            fx = get_fx_rate(ccy, base_ccy, trade["date"], fx_cache, yr)
        else:
            fx = 1.0
        val_native = trade["amount"] * price if price is not None else None
        val_base = val_native * fx if val_native is not None else None
        if trade["side"] == "Buy" and price is not None and current_price is not None:
            ret = (current_price / price) - 1
        else:
            ret = None
        enriched.append({
            **trade,
            "price": price,
            "fx": fx,
            "value_native": val_native,
            "value_base": val_base,
            "ret": ret,
        })

    total_bought = sum(t["amount"] for t in history if t["side"] == "Buy")
    total_sold = sum(abs(t["amount"]) for t in history if t["side"] == "Sell")
    net = total_bought - total_sold

    st.markdown(f"""
    <div style="display:flex;gap:1rem;margin:0.5rem 0 1.5rem 0;">
      <div style="flex:1;padding:0.8rem 1.2rem;border-radius:0.75rem;background:{T["card_bg"]};border:1px solid {T["border"]};text-align:center;">
        <div style="font-size:0.75rem;color:{T["text_faint"]};text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem;">Bought</div>
        <div style="font-size:1.4rem;font-weight:700;color:#22c55e;">{total_bought:.4f}</div>
      </div>
      <div style="flex:1;padding:0.8rem 1.2rem;border-radius:0.75rem;background:{T["card_bg"]};border:1px solid {T["border"]};text-align:center;">
        <div style="font-size:0.75rem;color:{T["text_faint"]};text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem;">Sold</div>
        <div style="font-size:1.4rem;font-weight:700;color:#ef4444;">{total_sold:.4f}</div>
      </div>
      <div style="flex:1;padding:0.8rem 1.2rem;border-radius:0.75rem;background:{T["card_bg"]};border:1px solid {T["border"]};text-align:center;">
        <div style="font-size:0.75rem;color:{T["text_faint"]};text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem;">Net</div>
        <div style="font-size:1.4rem;font-weight:700;color:{T["text"]};">{net:.4f}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Price chart with buy/sell markers ──────────────────────────────────────
    first_trade_date = date.fromisoformat(history[0]["date"])
    last_trade_date = date.fromisoformat(history[-1]["date"])
    chart_start = first_trade_date.replace(year=first_trade_date.year - 1) if first_trade_date.month > 1 else first_trade_date.replace(year=first_trade_date.year - 1)

    all_prices: dict[str, float] = {}
    for yr in range(chart_start.year, today.year + 1):
        year_data = storage.load_price_year(ticker, yr)
        all_prices.update(year_data)

    if all_prices:
        sorted_dates = sorted(all_prices.keys())
        price_dates = [date.fromisoformat(d) for d in sorted_dates]
        price_values = [all_prices[d] for d in sorted_dates]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=price_dates, y=price_values,
            mode="lines", name="Price",
            line=dict(color="#6C63FF", width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
        ))

        buys = [t for t in enriched if t["side"] == "Buy" and t["price"] is not None]
        sells = [t for t in enriched if t["side"] == "Sell" and t["price"] is not None]

        if buys:
            fig.add_trace(go.Scatter(
                x=[date.fromisoformat(t["date"]) for t in buys],
                y=[t["price"] for t in buys],
                mode="markers", name="Buy",
                marker=dict(color="#22c55e", size=12, symbol="triangle-up"),
                hovertemplate="%{x|%Y-%m-%d}<br>Buy %{y:.2f}<extra></extra>",
            ))
        if sells:
            fig.add_trace(go.Scatter(
                x=[date.fromisoformat(t["date"]) for t in sells],
                y=[t["price"] for t in sells],
                mode="markers", name="Sell",
                marker=dict(color="#ef4444", size=12, symbol="triangle-down"),
                hovertemplate="%{x|%Y-%m-%d}<br>Sell %{y:.2f}<extra></extra>",
            ))

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Price",
            template=T["plotly_template"],
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(
                rangeslider=dict(visible=True, thickness=0.05),
                rangeselector=dict(
                    buttons=[
                        dict(count=1, label="1M", step="month", stepmode="backward"),
                        dict(count=3, label="3M", step="month", stepmode="backward"),
                        dict(count=6, label="6M", step="month", stepmode="backward"),
                        dict(count=1, label="1Y", step="year", stepmode="backward"),
                        dict(step="all", label="All"),
                    ],
                    bgcolor=T["range_bg"],
                    activecolor=T["range_active"],
                    font=dict(color=T["text"]),
                ),
            ),
        )

        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    trade_df = pd.DataFrame([{
        "Date": t["date"],
        "Side": t["side"],
        "Shares": f'{t["amount"]:.4f}' if t["amount"] is not None else None,
        "Price": f'{t["price"]:.2f}' if t["price"] is not None else None,
        "Value": f'{t["value_native"]:.2f}' if t["value_native"] is not None else None,
        "FX": f'{t["fx"]:.4f}' if ccy != base_ccy and t["fx"] is not None else None,
        f"Value ({base_ccy})": f'{t["value_base"]:.2f}' if t["value_base"] is not None else None,
        "Return": f'{t["ret"] * 100:.1f}%' if t["ret"] is not None else None,
    } for t in enriched])

    import streamlit.components.v1 as components

    headers = list(trade_df.columns)
    rows_html = ""
    for _, row in trade_df.iterrows():
        cells = "".join(f"<td style='padding:4px 12px;border-bottom:1px solid #333'>{row[h]}</td>" for h in headers)
        rows_html += f"<tr>{cells}</tr>"
    header_html = "".join(f"<th style='padding:4px 12px;border-bottom:2px solid #555;text-align:left;font-weight:600'>{h}</th>" for h in headers)
    components.html(
        f"""<style>
        body {{ margin:0; font-family:system-ui,-apple-system,sans-serif; background:transparent; color:{T["table_text"]}; }}
        table {{ width:100%; border-collapse:collapse; font-size:24px; }}
        tr:hover {{ background:rgba(255,255,255,0.05); }}
        </style>
        <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{rows_html}</tbody>
        </table>""",
        height=50 + 48 * len(trade_df),
        scrolling=True,
    )

# ── Holdings table ────────────────────────────────────────────────────────────

if latest["assets"]:
    total_val = latest["total_value"] or 1.0
    bal = storage.load_balance()

    rows = []
    avg_fx_cache: dict = {}
    ticker_names = {a["ticker"]: get_ticker_name(a["ticker"]) for a in latest["assets"]}
    for a in sorted(latest["assets"], key=lambda x: x["value_base"], reverse=True):
        ticker = a["ticker"]
        shares = a["amount"]
        value = a["value_base"]
        avg_raw = bal.get(ticker, {}).get("avg_price", 0.0)
        ticker_ccy = a.get("currency", "PLN")
        if ticker_ccy != base_ccy:
            avg_ccy_fx = get_fx_rate(ticker_ccy, base_ccy, today.isoformat(), avg_fx_cache, today.year)
        else:
            avg_ccy_fx = 1.0
        avg = avg_raw * avg_ccy_fx
        cost_basis = shares * avg
        ret_pct = ((value / cost_basis) - 1) * 100 if cost_basis else 0.0
        rows.append({
            "ticker": ticker,
            "name": ticker_names.get(ticker, ticker),
            "ccy": a.get("currency", "—"),
            "weight": value / total_val * 100,
            "shares": shares,
            "value": value,
            "ret_pct": ret_pct,
        })

    def _fmt_val(v: float) -> str:
        s = f"{v:,.1f}".replace(",", " ")
        return f"{SYM.get(base_ccy, '')}{s}" if base_ccy != "PLN" else f"{s} PLN"

    def _fmt_ret(p: float) -> str:
        return f"{p:+.1f}%"

    def _ret_color(p: float) -> str:
        return "#3fb950" if p >= 0 else "#f85149"

    max_weight = max((r["weight"] for r in rows), default=1) or 1

    st.markdown(f"""
    <style>
    .holdings-row {{ border-bottom:1px solid {T["holdings_bar_bg"]}; }}
    .holdings-row:last-child {{ border-bottom:none; }}
    .h-hdr {{ border-bottom:2px solid {T["border"]}; padding:0; margin-bottom:4px; }}
    .h-col-hdr {{ color:{T["text_muted"]}; font-size:0.75rem; font-weight:700;
        text-transform:uppercase; letter-spacing:0.08em; text-align:center; display:block;
        padding:0.5rem 0; background:{T["card_faint"]}; border-radius:0.5rem; }}
    .h-cell {{ padding:12px 0; font-size:1.5rem; font-family:sans-serif; color:{T["text_cell"]}; text-align:center; }}
    .h-ticker {{ position:relative; overflow:hidden; }}
    .h-bar {{ position:absolute; top:0; left:0; height:100%; opacity:0.10;
        border-radius:4px; transition:width 0.3s ease; }}
    .h-name {{ position:relative; font-weight:600; color:{T["text"]}; font-size:1.5rem; }}
    .h-sub {{ position:relative; display:block; font-size:0.85em; color:{T["text_muted"]}; font-weight:400; }}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ font-size:0.75rem; }}
    </style>
    """, unsafe_allow_html=True)

    _hdr = st.columns([5, 1, 1, 1, 2, 1])
    for _ch, _label in zip(_hdr, ["Ticker", "CCY", "Weight", "Shares", "Value", "Return %"]):
        with _ch:
            st.markdown(f"<span class='h-col-hdr'>{_label}</span>", unsafe_allow_html=True)
    st.markdown("<div class='h-hdr'></div>", unsafe_allow_html=True)

    for r in rows:
        bar_pct = r["weight"]
        ret_col = _ret_color(r["ret_pct"])

        _c1, _c2, _c3, _c4, _c5, _c6 = st.columns([5, 1, 1, 1, 2, 1])
        with _c1:
            btn_label = f"{r['ticker']}  |  {r['name']}" if r["name"] != r["ticker"] else r["ticker"]
            if st.button(
                btn_label,
                key=f"hbtn_{r['ticker']}",
                help=f"Trade history for {r['ticker']}",
                use_container_width=True,
            ):
                _show_trade_dialog(r["ticker"], r["name"], r["ccy"])
            st.markdown(
                f"<div style='margin-top:-0.6rem;margin-bottom:0.2rem;border-radius:4px;overflow:hidden;height:4px;background:{T["holdings_bar_bg"]};'>"
                f"<div style='width:{bar_pct / max_weight * 100:.1f}%;height:100%;background:#6C63FF;border-radius:4px;'></div></div>",
                unsafe_allow_html=True,
            )
        with _c2:
            st.markdown(f"<div class='h-cell'>{r['ccy']}</div>", unsafe_allow_html=True)
        with _c3:
            st.markdown(f"<div class='h-cell'>{r['weight']:.1f}%</div>", unsafe_allow_html=True)
        with _c4:
            st.markdown(f"<div class='h-cell'>{r['shares']:.4f}</div>", unsafe_allow_html=True)
        with _c5:
            st.markdown(f"<div class='h-cell'>{_fmt_val(r['value'])}</div>", unsafe_allow_html=True)
        with _c6:
            st.markdown(f"<div class='h-cell' style='color:{ret_col};font-weight:600'>{_fmt_ret(r['ret_pct'])}</div>", unsafe_allow_html=True)
        st.markdown("<div class='holdings-row'></div>", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────

st.caption(
    f":material/info: Yahoo Finance · {today} · {base_ccy} · "
    f"Daily · {len(latest.get('assets', [])) if latest else 0} positions"
)

# ── Late-stage theme override (injected last, beats Streamlit's dark CSS) ──
st.markdown(f"""<style>
    /* Portalled dropdown menus — override Streamlit dark theme */
    [data-theme="dark"] [data-baseweb="popover"],
    [data-baseweb="popover"],
    [data-baseweb="popover"] > div {{
        background: {T["panel_bg"]} !important;
        border-color: {T["border"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"],
    [data-theme="dark"] [data-baseweb="menu"] > div,
    [data-theme="dark"] [data-baseweb="menu"] > ul,
    [data-baseweb="menu"],
    [data-baseweb="menu"] > div,
    [data-baseweb="menu"] > ul {{
        background: {T["panel_bg"]} !important;
    }}
    [data-theme="dark"] [role="option"],
    [data-theme="dark"] [role="listbox"] > div,
    [role="option"],
    [role="listbox"] > div {{
        background: {T["panel_bg"]} !important;
        color: {T["text"]} !important;
    }}
    [data-theme="dark"] [role="option"]:hover,
    [data-theme="dark"] [role="listbox"] > div:hover,
    [role="option"]:hover,
    [role="listbox"] > div:hover {{
        background: {T["card_bg"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"] [role="option"],
    [data-baseweb="menu"] [role="option"] {{
        background-color: {T["panel_bg"]} !important;
        color: {T["text"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"] [role="option"]:hover,
    [data-baseweb="menu"] [role="option"]:hover,
    [data-theme="dark"] [role="option"]:focus,
    [data-theme="dark"] [role="option"]:active,
    [data-theme="dark"] [role="option"][aria-selected="true"],
    [role="option"]:focus,
    [role="option"]:active,
    [role="option"][aria-selected="true"] {{
        background-color: {T["card_bg"]} !important;
        color: {T["text"]} !important;
    }}
    /* Streamlit active-option class */
    [data-theme="dark"] [data-baseweb="option"],
    [data-baseweb="option"] {{
        background-color: {T["panel_bg"]} !important;
        color: {T["text"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="option"]:hover,
    [data-theme="dark"] [data-baseweb="option"]:focus,
    [data-theme="dark"] [data-baseweb="option"]:active,
    [data-baseweb="option"]:hover,
    [data-baseweb="option"]:focus,
    [data-baseweb="option"]:active {{
        background-color: {T["card_bg"]} !important;
    }}
    /* Streamlit's own highlight/focus ring */
    [data-theme="dark"] [data-baseweb="menu"] li[aria-selected],
    [data-baseweb="menu"] li[aria-selected] {{
        background-color: {T["card_bg"]} !important;
        color: {T["text"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"] li[aria-selected]:focus,
    [data-theme="dark"] [data-baseweb="menu"] li[aria-selected]:hover,
    [data-baseweb="menu"] li[aria-selected]:focus,
    [data-baseweb="menu"] li[aria-selected]:hover {{
        background-color: {T["card_bg"]} !important;
    }}
    /* Streamlit sets these CSS vars for BaseWeb theming */
    /* BaseWeb + Streamlit dark theme CSS vars — apply in BOTH modes */
    :root,
    [data-theme="dark"] {{
        --SDS-colorBackground-body: {T["page_bg"]};
        --SDS-colorBackground-iteration0: {T["panel_bg"]};
        --SDS-colorBackground-constructionRotation0: {T["card_bg"]};
        --SDS-colorBase-positive: {T["accent"]};
        --secondary-background-color: {T["panel_bg"]};
    }}
    /* Expander — override dark background entirely (Streamlit paints #1F2328
       on the <details> box AND on the emotion-cache wrapper spans inside <summary>) */
    details[data-testid="stExpander"] {{
        background-color: {T["panel_bg"]} !important;
        border-color: {T["border_strong"]} !important;
    }}
    details[data-testid="stExpander"] summary {{
        background-color: {T["panel_bg"]} !important;
        color: {T["text"]} !important;
    }}
    details[data-testid="stExpander"] summary * {{
        background-color: transparent !important;
        color: {T["text"]} !important;
    }}
    details[data-testid="stExpander"] summary:hover,
    details[data-testid="stExpander"] summary:focus,
    details[data-testid="stExpander"] summary:active {{
        background-color: {T["card_bg"]} !important;
        outline: none !important;
    }}
    /* Dialog (portalled) — override Streamlit's dark modal background.
       The outer dialog element carries role="dialog" (class .st-bb paints #0F172A),
       and does NOT have data-testid="stDialog", so target role="dialog" too. */
    [role="dialog"],
    [data-testid="stDialog"],
    [role="dialog"] > div,
    [data-testid="stDialog"] > div,
    [role="dialog"] [data-testid="stVerticalBlock"],
    [data-testid="stDialog"] [data-testid="stVerticalBlock"] {{
        background-color: {T["panel_bg"]} !important;
    }}
    [role="dialog"],
    [data-testid="stDialog"],
    [role="dialog"] > div,
    [data-testid="stDialog"] > div {{
        border: 1px solid {T["border_strong"]} !important;
    }}
    [role="dialog"] button[aria-label="Close"],
    [data-testid="stDialog"] button[aria-label="Close"] {{
        color: {T["text"]} !important;
        background-color: transparent !important;
    }}
    [role="dialog"] button[aria-label="Close"]:hover,
    [data-testid="stDialog"] button[aria-label="Close"]:hover {{
        background-color: {T["card_bg"]} !important;
    }}
    /* BaseWeb tooltip (button help text, e.g. "Trade history for SXRV.DE") */
    [data-baseweb="tooltip"],
    .stTooltipContent {{
        background-color: {T["panel_bg"]} !important;
        color: {T["text"]} !important;
        border: 1px solid {T["border_strong"]} !important;
        --colorBackgroundTooltip: {T["panel_bg"]};
    }}
    [data-baseweb="tooltip"] *,
    [data-baseweb="tooltip"] div {{
        background-color: {T["panel_bg"]} !important;
        color: {T["text"]} !important;
    }}
</style>""", unsafe_allow_html=True)

# ── JS injection: beat Streamlit's dynamically-injected emotion-cache CSS ──────
import streamlit.components.v1 as components

components.html(f"""
<script>
(function() {{
    var doc;
    try {{ doc = window.parent.document; }} catch(e) {{ doc = document; }}
    function injectExpanderFix() {{
        var id = 'negotium-expander-fix';
        var existing = doc.getElementById(id);
        if (existing) existing.parentNode.removeChild(existing);
        var s = doc.createElement('style');
        s.id = id;
        s.innerHTML =
            '[data-testid="stExpander"]{{' +
                'background-color:{T["panel_bg"]} !important;' +
                'border-color:{T["border_strong"]} !important;' +
            '}}' +
            '[data-testid="stExpander"] summary{{' +
                'background-color:{T["panel_bg"]} !important;' +
                'color:{T["text"]} !important;' +
            '}}' +
            '[data-testid="stExpander"] summary *{{' +
                'background-color:transparent !important;' +
                'color:{T["text"]} !important;' +
            '}}' +
            '[data-testid="stExpander"] summary:hover,' +
            '[data-testid="stExpander"] summary:focus,' +
            '[data-testid="stExpander"] summary:active{{' +
                'background-color:{T["card_bg"]} !important;' +
                'outline:none !important;' +
            '}}' +
            /* Multiselect/select placeholder text ("Choose options").
               Streamlit's BaseWeb StyledPlaceholder uses emotion class "st-fh"
               (no stable id). Its own rule has no !important, so we win.
               Also recolor any select element still painted with the dark-muted
               placeholder color rgba(241,245,249,0.6) — resilient to class renames. */
            '.st-fh{{color:{T["text"]} !important;}}';
        doc.head.appendChild(s);
        function fixPlaceholderColors() {{
            var muted = 'rgba(241, 245, 249, 0.6)';
            var selects = doc.querySelectorAll('[data-baseweb="select"]');
            for (var i = 0; i < selects.length; i++) {{
                var divs = selects[i].querySelectorAll('div');
                for (var j = 0; j < divs.length; j++) {{
                    var st = (doc.defaultView || window).getComputedStyle(divs[j]);
                    if (st.color === muted && divs[j].textContent.trim() !== '') {{
                        divs[j].style.color = '{T["text"]}';
                    }}
                }}
            }}
        }}
        fixPlaceholderColors();
        setTimeout(fixPlaceholderColors, 300);
    }}
    injectExpanderFix();
    setTimeout(injectExpanderFix, 300);
}})();
</script>
""", height=0, width=0)

