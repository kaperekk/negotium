"""Compatibility layer for UI styling modules.

The application keeps CSS and HTML helpers split by concern so the Python view
logic stays focused on orchestration and rendering flows rather than large style
blocks.
"""

from __future__ import annotations

from ui.style_base import (
    build_app_styles,
    build_late_theme_override,
    build_streamlit_fix_script,
)
from ui.style_components import (
    build_holdings_styles,
    build_metric_card_styles,
    build_toggle_button_styles,
    build_trade_dialog_styles,
    render_empty_state,
    render_metric_cards,
    render_project_banner,
    render_trade_empty_state,
    render_trade_summary_cards,
    render_trade_table_html,
)

__all__ = [
    "build_app_styles",
    "build_trade_dialog_styles",
    "build_holdings_styles",
    "build_metric_card_styles",
    "build_toggle_button_styles",
    "render_project_banner",
    "render_empty_state",
    "render_trade_empty_state",
    "render_trade_summary_cards",
    "render_metric_cards",
    "render_trade_table_html",
    "build_late_theme_override",
    "build_streamlit_fix_script",
]
