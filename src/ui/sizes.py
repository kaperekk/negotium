"""Centralized UI size constants for Negotium.

Every tunable size (font, spacing, chart height, etc.) lives here so the
overall density of the app can be adjusted in one place.  Files across
``src/ui/`` should import from this module instead of hard-coding values.

The values below produce a *compact* layout.  To make the UI larger,
increase the values (or scale them via a multiplier).
"""

from __future__ import annotations

# ── Root & Layout ────────────────────────────────────────────────────────────
# Base font-size applied to <html>/<body>.  All ``rem`` values throughout the
# app cascade from this root.
ROOT_FONT_PX: int = 11

# Sidebar width in pixels.
SIDEBAR_WIDTH_PX: int = 200

# Main content container padding (applied to .block-container).
CONTAINER_PADDING_TOP_REM: float = 3.0
CONTAINER_PADDING_LEFT_REM: float = 1.0
CONTAINER_PADDING_RIGHT_REM: float = 1.0

# ── Chart Heights (px) ──────────────────────────────────────────────────────
CHART_HEIGHT_PORTFOLIO: int = 600
CHART_HEIGHT_ALLOCATION: int = 350
CHART_HEIGHT_DRAWDOWN: int = 200
CHART_HEIGHT_WATCHLIST: int = 130

# Streamlit text_area height in the sidebar (ticker rules).
SIDEBAR_TEXT_AREA_HEIGHT: int = 120

# ── Chart Font Sizes (px) ───────────────────────────────────────────────────
# Shared across multiple chart files via this module.
HOVER_LABEL_SIZE: int = 16
AXIS_TICK_FONT_SIZE: int = 10
AXIS_TITLE_FONT_SIZE: int = 11

# Per-chart font sizes (Plotly ``font=dict(size=…)``).
PORTFOLIO_TICK_FONT: int = 10
PORTFOLIO_TITLE_FONT: int = 10
PORTFOLIO_GLOBAL_FONT: int = 10

ALLOCATION_PIE_TEXT_FONT: int = 14
ALLOCATION_GLOBAL_FONT: int = 11
ALLOCATION_LEGEND_FONT: int = 14

DRAWDOWN_ANNOTATION_FONT: int = 12
DRAWDOWN_GLOBAL_FONT: int = 12

# ── Component Font Sizes (rem) ──────────────────────────────────────────────
# Metric card value (Streamlit st.metric).
METRIC_VALUE_FONT_REM: float = 1.2

# Sidebar heading (h1).
SIDEBAR_HEADING_FONT_REM: float = 1.2

# Holdings table.
HOLDINGS_CELL_FONT_REM: float = 1.0
HOLDINGS_NAME_FONT_REM: float = 1.0
HOLDINGS_COL_HEADER_FONT_REM: float = 0.65

# Stat cards (portfolio summary row).
STAT_CARD_LABEL_FONT_REM: float = 0.65
STAT_CARD_VALUE_FONT_REM: float = 0.9

# Toggle buttons (currency switch, period selector).
TOGGLE_BUTTON_FONT_REM: float = 1.1
TOGGLE_BUTTON_TEXT_FONT_REM: float = 0.9

# Form submit buttons (Add row / Remove row).
FORM_SUBMIT_FONT_REM: float = 0.8

# Project banner.
BANNER_TITLE_FONT_REM: float = 1.2

# Empty-state boxes.
EMPTY_STATE_ICON_FONT_REM: float = 1.5
EMPTY_STATE_TITLE_FONT_REM: float = 0.9
EMPTY_STATE_SUBTITLE_FONT_REM: float = 0.75
EMPTY_STATE_DETAILS_FONT_REM: float = 0.85

# Trade empty state.
TRADE_EMPTY_TITLE_FONT_REM: float = 0.85
TRADE_EMPTY_SUBTITLE_FONT_REM: float = 0.7

# Trade summary cards (Bought / Sold / Net).
TRADE_SUMMARY_VALUE_FONT_REM: float = 1.0
TRADE_SUMMARY_LABEL_FONT_REM: float = 0.75

# Trade dialog.
DIALOG_METRIC_FONT_REM: float = 2.0
DIALOG_HEADING_FONT_REM: float = 1.0

# Trade table (hardcoded px – not affected by rem root).
TRADE_TABLE_FONT_PX: int = 12

# ── Watchlist Font Sizes (rem) ──────────────────────────────────────────────
WATCHLIST_SYMBOL_FONT_REM: float = 1.2
WATCHLIST_NAME_FONT_REM: float = 0.75
WATCHLIST_PRICE_FONT_REM: float = 0.9
WATCHLIST_PRICE_LABEL_FONT_REM: float = 0.6
WATCHLIST_PERIOD_FONT_REM: float = 0.72
WATCHLIST_CHANGE_FONT_REM: float = 0.9
WATCHLIST_NOTE_FONT_REM: float = 0.85
WATCHLIST_GRAB_CURSOR_FONT_PX: int = 12

# ── Sidebar Font Sizes (rem) ────────────────────────────────────────────────
SIDEBAR_LABEL_FONT_REM: float = 0.85
SIDEBAR_CAPTION_FONT_REM: float = 0.75

# ── Spacing (rem / px) ──────────────────────────────────────────────────────
# Stat card row.
STAT_ROW_GAP_REM: float = 1.0
STAT_ROW_MARGIN_TOP_REM: float = 0.5
STAT_ROW_MARGIN_BOTTOM_REM: float = 1.0

# Stat card internal padding.
STAT_CARD_PADDING_REM: str = "0.5rem 0.8rem"

# Toggle button padding & min-height.
TOGGLE_BUTTON_PADDING_PX: str = "6px 10px"
TOGGLE_BUTTON_MIN_HEIGHT_PX: int = 36

# Empty-state padding.
EMPTY_STATE_PADDING_REM: str = "1.2rem 1rem"
TRADE_EMPTY_PADDING_REM: str = "1rem 0.75rem"

# Trade summary cards gap.
TRADE_SUMMARY_GAP_REM: float = 1.0

# Sidebar horizontal block gap.
SIDEBAR_GAP_REM: float = 0.3

# ── Border Radius ───────────────────────────────────────────────────────────
BORDER_RADIUS_SM: str = "0.5rem"
BORDER_RADIUS_MD: str = "0.75rem"
BORDER_RADIUS_LG: str = "12px"
BORDER_RADIUS_BUTTON: int = 10

# ── Dialog ──────────────────────────────────────────────────────────────────
DIALOG_MIN_HEIGHT_VH: int = 75
DIALOG_WIDTH_VW: int = 95

__all__ = [
    "ROOT_FONT_PX",
    "SIDEBAR_WIDTH_PX",
    "CONTAINER_PADDING_TOP_REM",
    "CONTAINER_PADDING_LEFT_REM",
    "CONTAINER_PADDING_RIGHT_REM",
    "CHART_HEIGHT_PORTFOLIO",
    "CHART_HEIGHT_ALLOCATION",
    "CHART_HEIGHT_DRAWDOWN",
    "CHART_HEIGHT_WATCHLIST",
    "SIDEBAR_TEXT_AREA_HEIGHT",
    "HOVER_LABEL_SIZE",
    "AXIS_TICK_FONT_SIZE",
    "AXIS_TITLE_FONT_SIZE",
    "PORTFOLIO_TICK_FONT",
    "PORTFOLIO_TITLE_FONT",
    "PORTFOLIO_GLOBAL_FONT",
    "ALLOCATION_PIE_TEXT_FONT",
    "ALLOCATION_GLOBAL_FONT",
    "ALLOCATION_LEGEND_FONT",
    "DRAWDOWN_ANNOTATION_FONT",
    "DRAWDOWN_GLOBAL_FONT",
    "METRIC_VALUE_FONT_REM",
    "SIDEBAR_HEADING_FONT_REM",
    "HOLDINGS_CELL_FONT_REM",
    "HOLDINGS_NAME_FONT_REM",
    "HOLDINGS_COL_HEADER_FONT_REM",
    "STAT_CARD_LABEL_FONT_REM",
    "STAT_CARD_VALUE_FONT_REM",
    "TOGGLE_BUTTON_FONT_REM",
    "TOGGLE_BUTTON_TEXT_FONT_REM",
    "FORM_SUBMIT_FONT_REM",
    "BANNER_TITLE_FONT_REM",
    "EMPTY_STATE_ICON_FONT_REM",
    "EMPTY_STATE_TITLE_FONT_REM",
    "EMPTY_STATE_SUBTITLE_FONT_REM",
    "EMPTY_STATE_DETAILS_FONT_REM",
    "TRADE_EMPTY_TITLE_FONT_REM",
    "TRADE_EMPTY_SUBTITLE_FONT_REM",
    "TRADE_SUMMARY_VALUE_FONT_REM",
    "TRADE_SUMMARY_LABEL_FONT_REM",
    "DIALOG_METRIC_FONT_REM",
    "DIALOG_HEADING_FONT_REM",
    "TRADE_TABLE_FONT_PX",
    "WATCHLIST_SYMBOL_FONT_REM",
    "WATCHLIST_NAME_FONT_REM",
    "WATCHLIST_PRICE_FONT_REM",
    "WATCHLIST_PRICE_LABEL_FONT_REM",
    "WATCHLIST_PERIOD_FONT_REM",
    "WATCHLIST_CHANGE_FONT_REM",
    "WATCHLIST_NOTE_FONT_REM",
    "WATCHLIST_GRAB_CURSOR_FONT_PX",
    "SIDEBAR_LABEL_FONT_REM",
    "SIDEBAR_CAPTION_FONT_REM",
    "STAT_ROW_GAP_REM",
    "STAT_ROW_MARGIN_TOP_REM",
    "STAT_ROW_MARGIN_BOTTOM_REM",
    "STAT_CARD_PADDING_REM",
    "TOGGLE_BUTTON_PADDING_PX",
    "TOGGLE_BUTTON_MIN_HEIGHT_PX",
    "EMPTY_STATE_PADDING_REM",
    "TRADE_EMPTY_PADDING_REM",
    "TRADE_SUMMARY_GAP_REM",
    "SIDEBAR_GAP_REM",
    "BORDER_RADIUS_SM",
    "BORDER_RADIUS_MD",
    "BORDER_RADIUS_LG",
    "BORDER_RADIUS_BUTTON",
    "DIALOG_MIN_HEIGHT_VH",
    "DIALOG_WIDTH_VW",
]
