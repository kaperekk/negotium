"""Specific component styling and HTML fragments for dashboard UI."""

from __future__ import annotations

from ui.colors import NEGATIVE, POSITIVE


def build_trade_dialog_styles(theme: dict[str, str]) -> str:
    t = theme
    return f"""
    <style>
    [role="dialog"],
    [data-testid="stDialog"] {{ min-width:95vw !important; min-height:85vh !important; max-width:95vw !important; background-color:{t["panel_bg"]} !important; border:1px solid {t["border_strong"]} !important; }}
    [role="dialog"] > div,
    [data-testid="stDialog"] > div {{ width:100% !important; max-width:100% !important; height:100% !important; background-color:{t["panel_bg"]} !important; border:1px solid {t["border_strong"]} !important; }}
    [role="dialog"] [data-testid="stVerticalBlock"],
    [data-testid="stDialog"] [data-testid="stVerticalBlock"] {{ background-color:{t["panel_bg"]} !important; }}
    [data-testid="stDialog"] .stMetric label {{ font-size:3rem !important; }}
    [data-testid="stDialog"] .stMetric [data-testid="stMetricValue"] {{ font-size:3rem !important; }}
    [data-testid="stDialog"] h3 {{ font-size:1.5rem !important; font-weight:600 !important; color:{t["text_muted"]} !important; }}
    [role="dialog"] button[aria-label="Close"],
    [data-testid="stDialog"] button[aria-label="Close"] {{ color:{t["text"]} !important; background-color:transparent !important; }}
    [role="dialog"] button[aria-label="Close"]:hover,
    [data-testid="stDialog"] button[aria-label="Close"]:hover {{ background-color:{t["card_bg"]} !important; }}
    </style>
    """


def build_holdings_styles(theme: dict[str, str]) -> str:
    t = theme
    return f"""
    <style>
    .holdings-row {{ border-bottom:1px solid {t["holdings_bar_bg"]}; }}
    .holdings-row:last-child {{ border-bottom:none; }}
    .h-hdr {{ border-bottom:2px solid {t["border"]}; padding:0; margin-bottom:4px; }}
    .h-col-hdr {{ color:{t["text_muted"]}; font-size:0.75rem; font-weight:700;
        text-transform:uppercase; letter-spacing:0.08em; text-align:center; display:block;
        padding:0.5rem 0; background:{t["card_faint"]}; border-radius:0.5rem; }}
    .h-cell {{ padding:12px 0; font-size:1.5rem; font-family:sans-serif; color:{t["text_cell"]}; text-align:center; }}
    .h-ticker {{ position:relative; overflow:hidden; }}
    .h-bar {{ position:absolute; top:0; left:0; height:100%; opacity:0.10;
        border-radius:4px; transition:width 0.3s ease; }}
    .h-name {{ position:relative; font-weight:600; color:{t["text"]}; font-size:1.5rem; }}
    .h-sub {{ position:relative; display:block; font-size:0.85em; color:{t["text_muted"]}; font-weight:400; }}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ font-size:0.75rem; }}
    </style>
    """


def build_metric_card_styles(theme: dict[str, str]) -> str:
    t = theme
    return f"""
    <style>
    .stat-row {{ display:flex; gap:1rem; margin:0.5rem 0 1rem 0; }}
    .stat-card {{
      flex:1; padding:0.8rem 1.2rem; border-radius:0.75rem;
      background:{t["card_bg"]};
      border:1px solid {t["border"]};
    }}
    .stat-card .label {{ font-size:0.75rem; color:{t["text_faint"]}; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.2rem; text-align:center; }}
    .stat-card .value {{ font-size:1.4rem; font-weight:700; color:{t["text"]}; text-align:center; }}
    .green .value,
    .blue .value,
    .purple .value,
    .amber .value,
    .cyan .value {{ color:{t["text"]}; }}
    </style>
    """


def build_toggle_button_styles(theme: dict[str, str]) -> str:
    t = theme
    return f"""
    <style>
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="secondary"]) button[kind="secondary"],
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="primary"]) button[kind="primary"] {{
        background: {t["card_bg"]} !important;
        border: 1px solid {t["border"]} !important;
        border-radius: 16px !important;
        padding: 20px 24px !important;
        min-height: 85px !important;
        width: 100% !important;
        transition: all 0.2s ease !important;
        color: {t["text"]} !important;
        font-size: 1.7rem !important;
        font-weight: 600 !important;
    }}
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="secondary"]) button[kind="secondary"]:hover,
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="primary"]) button[kind="primary"]:hover {{
        border-color: {t["border_hover"]} !important;
    }}
    div[data-testid="stHorizontalBlock"] > div:has(button[kind="primary"]) button[kind="primary"] {{
        border-color: {t["border_active"]} !important;
        background: {t["card_btn_active"]} !important;
    }}
    div[data-testid="stHorizontalBlock"] button p {{
        font-size: 1.4rem !important;
        font-weight: 600 !important;
    }}
    </style>
    """


def render_project_banner(project_name: str, theme: dict[str, str]) -> str:
    t = theme
    return f"""
    <div style="
        padding:0.8rem 1.2rem; border-radius:0.75rem; text-align:center;
        background:{t["card_bg"]}; border:1px solid {t["border"]};
        margin-top:-1rem; margin-bottom:0.5rem;
    ">
        <div style="font-size:1.6rem; font-weight:700; color:{t["text"]};">📈 {project_name}</div>
    </div>
    """


def render_empty_state(title: str, subtitle: str, theme: dict[str, str], *, details: str | None = None, icon: str = "📈") -> str:
    t = theme
    details_html = ""
    if details:
        details_html = f'<div style="font-size:0.85rem;color:{t["text_muted"]};">{details}</div>'
    return f"""
    <div style="text-align:center;padding:4rem 2rem;border-radius:1rem;background:{t["card_bg"]};border:1px solid {t["border"]};margin:2rem 0;">
        <div style="font-size:3rem;margin-bottom:1rem;">{icon}</div>
        <div style="font-size:1.4rem;font-weight:600;color:{t["text"]};margin-bottom:0.5rem;">{title}</div>
        <div style="font-size:1rem;color:{t["text_muted"]};margin-bottom:0.3rem;">{subtitle}</div>
        {details_html}
    </div>
    """


def render_trade_empty_state(theme: dict[str, str]) -> str:
    t = theme
    return f"""
    <div style="text-align:center;padding:3rem 2rem;border-radius:1rem;background:{t["card_bg"]};border:1px solid {t["border"]};margin:1rem 0;">
        <div style="font-size:1.2rem;font-weight:600;color:{t["text"]};margin-bottom:0.3rem;">No trades found</div>
        <div style="font-size:0.9rem;color:{t["text_muted"]};">This position has no trade history yet.</div>
    </div>
    """


def render_trade_summary_cards(theme: dict[str, str], total_bought: float, total_sold: float, net: float) -> str:
    t = theme
    return f"""
    <div style="display:flex;gap:1rem;margin:0.5rem 0 1.5rem 0;">
      <div style="flex:1;padding:0.8rem 1.2rem;border-radius:0.75rem;background:{t["card_bg"]};border:1px solid {t["border"]};text-align:center;">
        <div style="font-size:0.75rem;color:{t["text_faint"]};text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem;">Bought</div>
        <div style="font-size:1.4rem;font-weight:700;color:{POSITIVE};">{total_bought:.4f}</div>
      </div>
      <div style="flex:1;padding:0.8rem 1.2rem;border-radius:0.75rem;background:{t["card_bg"]};border:1px solid {t["border"]};text-align:center;">
        <div style="font-size:0.75rem;color:{t["text_faint"]};text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem;">Sold</div>
        <div style="font-size:1.4rem;font-weight:700;color:{NEGATIVE};">{total_sold:.4f}</div>
      </div>
      <div style="flex:1;padding:0.8rem 1.2rem;border-radius:0.75rem;background:{t["card_bg"]};border:1px solid {t["border"]};text-align:center;">
        <div style="font-size:0.75rem;color:{t["text_faint"]};text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem;">Net</div>
        <div style="font-size:1.4rem;font-weight:700;color:{t["text"]};">{net:.4f}</div>
      </div>
    </div>
    """


def render_metric_cards(theme: dict[str, str], *,
                        total_value: str,
                        invested: str,
                        largest_position: str,
                        cagr: str,
                        irr: str,
                        base_ccy: str) -> str:
    t = theme
    return f"""
    <div class="stat-row">
      <div class="stat-card cyan" title="Current market value of all holdings in {base_ccy}">
        <div class="label">Total Value</div>
        <div class="value">{total_value}</div>
      </div>
      <div class="stat-card blue" title="Net deposits minus withdrawals across all accounts">
        <div class="label">Invested</div>
        <div class="value">{invested}</div>
      </div>
      <div class="stat-card purple" title="The position with the highest current value">
        <div class="label">Largest Position</div>
        <div class="value">{largest_position}</div>
      </div>
      <div class="stat-card green" title="Compound Annual Growth Rate — smoothed yearly return since first deposit">
        <div class="label">CAGR</div>
        <div class="value">{cagr}</div>
      </div>
      <div class="stat-card amber" title="Internal Rate of Return — accounts for exact timing of every deposit">
        <div class="label">IRR</div>
        <div class="value">{irr}</div>
      </div>
    </div>
    """


def render_trade_table_html(theme: dict[str, str], trade_df) -> str:
    t = theme
    headers = list(trade_df.columns)
    rows_html = ""
    for _, row in trade_df.iterrows():
        cells = "".join(f"<td style='padding:4px 12px;border-bottom:1px solid {t['table_border']}'>{row[h]}</td>" for h in headers)
        rows_html += f"<tr>{cells}</tr>"
    header_html = "".join(f"<th style='padding:4px 12px;border-bottom:2px solid {t['table_header_border']};text-align:left;font-weight:600'>{h}</th>" for h in headers)
    return f"""
    <style>
    body {{ margin:0; font-family:system-ui,-apple-system,sans-serif; background:transparent; color:{t["table_text"]}; }}
    table {{ width:100%; border-collapse:collapse; font-size:24px; }}
    tr:hover {{ background:{t["table_hover"]}; }}
    </style>
    <table>
    <thead><tr>{header_html}</tr></thead>
    <tbody>{rows_html}</tbody>
    </table>
    """
