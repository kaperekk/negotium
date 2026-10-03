"""
app_local.py — Negotium - Investment Tracker UI (Streamlit) Direct Access

Run: streamlit run src/app_local.py

This version directly uses the default user without login.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from app_core import (
    inject_styles,
    inject_theme_veil,
    init_runtime_with_user,
    render_main_app,
    setup_page_config,
)


def main() -> None:
    """Main entry point with default user."""
    setup_page_config()

    cfg, storage_mod, _theme_name, T, today = init_runtime_with_user()

    inject_styles(T)
    inject_theme_veil(T)
    render_main_app(cfg, storage_mod, T, today)


if __name__ == "__main__":
    main()