"""
colors.py — single source of truth for all UI colours and themes.

Contains the per-theme palettes (THEMES / get_theme), theme-independent
semantic colours (accent, positive/negative, etc.) and the benchmark palette.
Other modules should import from here instead of hard-coding hex values.
"""
from __future__ import annotations

# ── Themes ────────────────────────────────────────────────────────────────────

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "card_bg": "rgba(34,38,45,0.7)",
        "border": "rgba(255,255,255,0.10)",
        "border_hover": "rgba(255,255,255,0.22)",
        "border_active": "rgba(255,255,255,0.20)",
        "border_strong": "#4A515C",
        "text": "#E6EDF3",
        "text_cell": "#C9D1D9",
        "hover_text": "#FFFFFF",
        "text_muted": "#8B949E",
        "text_faint": "rgba(255,255,255,0.5)",
        "panel_bg": "#2A2F38",
        "chart_bg": "#1E2228",
        "hr": "#343A43",
        "accent": "#6C63FF",
        "accent_tag_bg": "rgba(108,99,255,0.2)",
        "accent_tag_border": "rgba(108,99,255,0.4)",
        "accent_tag_hover": "rgba(108,99,255,0.3)",
        "card_btn_active": "rgba(255,255,255,0.05)",
        "card_faint": "rgba(255,255,255,0.04)",
        "chart_grid": "rgba(48,54,61,0.6)",
        "chart_zeroline": "rgba(48,54,61,0.8)",
        "hover_bg": "rgba(42,47,56,0.95)",
        "plotly_template": "plotly_dark",
        "page_bg": "#181B20",
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
        "hover_text": "#1F2328",
        "text_muted": "#656D76",
        "text_faint": "rgba(0,0,0,0.45)",
        "panel_bg": "#F3F5F8",
        "chart_bg": "#F3F5F8",
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
        "page_bg": "#EAEDEF",
        "range_bg": "rgba(0,0,0,0.04)",
        "range_active": "rgba(108,99,255,0.15)",
        "table_border": "#D0D7DE",
        "table_header_border": "#AFB8C1",
        "table_hover": "rgba(0,0,0,0.04)",
        "table_text": "#24292F",
        "holdings_bar_bg": "rgba(0,0,0,0.05)",
    },
}


def get_theme(theme_name: str) -> dict[str, str]:
    """Return a palette dict, defaulting safely to dark mode."""
    return THEMES.get(theme_name, THEMES["dark"]).copy()


# ── Semantic (theme-independent) colours ──────────────────────────────────────

ACCENT = "#6C63FF"
ACCENT_FILL = "rgba(108,99,255,0.08)"
MUTED_LINE = "#94a3b8"

POSITIVE = "#22c55e"   # gains / buys
NEGATIVE = "#ef4444"   # losses / sells
RETURN_UP = "#3fb950"  # holdings return % (green)
DIVIDEND = "#eab308"   # dividend markers / gold

# Shared size for chart hover-label text (watchlist, portfolio, drawdown).
HOVER_LABEL_SIZE = 30

# Shared axis label/tick font sizes.
AXIS_TICK_FONT_SIZE = 16
AXIS_TITLE_FONT_SIZE = 18


# ── Benchmark palette ─────────────────────────────────────────────────────────

BENCHMARKS: dict[str, str] = {
    "NASDAQ 100 (SXRV.DE)": "SXRV.DE",
    "S&P 500 (I500.DE)": "I500.DE",
    "Vanguard FTSE All-World (VWCE.DE)": "VWCE.DE",
    "Emerging Markets (IS3N.DE)": "IS3N.DE",
    "Bitcoin (BTCE.DE)": "BTCE.DE",
    "Gold (4GLD.DE)": "4GLD.DE",
}

BENCH_COLORS: dict[str, str] = {
    "NASDAQ 100 (SXRV.DE)": "#06b6d4",
    "S&P 500 (I500.DE)": "#22c55e",
    "Vanguard FTSE All-World (VWCE.DE)": "#f97316",
    "Emerging Markets (IS3N.DE)": "#8b5cf6",
    "Bitcoin (BTCE.DE)": "#ef4444",
    "Gold (4GLD.DE)": "#eab308",
}
