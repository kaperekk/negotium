"""Application styling - CSS and HTML helpers for the Streamlit UI.

All theme-aware CSS is built from a theme dict (see ui.colors). Functions
returning HTML <style> blocks are injected via st.markdown(unsafe_allow_html=True).
"""

from __future__ import annotations

from ui.colors import NEGATIVE, POSITIVE


# Base app styles


def build_app_styles(theme: dict[str, str]) -> str:
    """Return the CSS used for the app shell and widgets."""
    t = theme
    return f"""
    <style>
        html, body, [class*="css"] {{ font-size: 18px !important; }}

        .stApp {{ background-color: {t["page_bg"]}; }}
        [data-testid="stHeader"] {{ background-color: {t["page_bg"]}; }}
        section[data-testid="stSidebar"] {{ background-color: {t["panel_bg"]}; }}
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ background-color: {t["panel_bg"]}; }}

        :root, [data-theme="dark"] {{
            --background-color: {t["page_bg"]};
            --secondary-background-color: {t["panel_bg"]};
            --text-color: {t["text"]};
            --primary-color: {t["accent"]};
            --sidebar-width: 400px;
        }}

        [data-baseweb="select"] {{
            background-color: {t["card_bg"]} !important;
            color: {t["text"]} !important;
            border-color: {t["border"]} !important;
        }}
        [data-baseweb="select"] > div {{ background-color: {t["card_bg"]} !important; }}
        [data-baseweb="input"] {{
            background-color: {t["card_bg"]} !important;
            color: {t["text"]} !important;
        }}
        [data-baseweb="tag"] {{
            background-color: {t["accent_tag_bg"]} !important;
            color: {t["text"]} !important;
        }}
        .stMarkdown p, .stMarkdown li, .stMarkdown span, .stMarkdown div,
        .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
        .stMarkdown h5, .stMarkdown h6 {{ color: {t["text"]}; }}
        .stCaption p, .stCaption span {{ color: {t["text_muted"]}; }}
        h1, h2, h3, h4, h5, h6 {{ color: {t["text"]}; }}
        label, [data-baseweb="label"] {{ color: {t["text"]} !important; }}
        input, textarea, select {{ color: {t["text"]} !important; }}
        .st-gd {{ color: {t["text"]} !important; opacity: 1 !important; }}
        p, li, span {{ color: {t["text"]}; }}

        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input {{
            background: {t["card_bg"]} !important;
            color: {t["text"]} !important;
            border-color: {t["border"]} !important;
        }}
        [data-testid="stTextInput"] > div > div,
        [data-testid="stTextArea"] > div > div,
        [data-testid="stNumberInput"] > div > div {{
            background: {t["card_bg"]} !important;
            border-color: {t["border"]} !important;
        }}
        [data-testid="stSelectbox"] > div > div,
        [data-testid="stSelectbox"] [data-baseweb="select"],
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] > div > div,
        [data-testid="stMultiSelect"] [data-baseweb="select"],
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
            background: {t["card_bg"]} !important;
            border: 1px solid {t["border"]} !important;
            border-radius: 0.75rem !important;
            color: {t["text"]} !important;
        }}
        [data-testid="stMultiSelect"] input,
        [data-testid="stSelectbox"] input {{
            background: {t["card_bg"]} !important;
            color: {t["text"]} !important;
        }}
        [data-testid="stMultiSelect"] [data-baseweb="tag"] {{
            background: {t["accent_tag_bg"]} !important;
            border: 1px solid {t["accent_tag_border"]} !important;
            border-radius: 0.5rem !important;
            color: {t["text"]} !important;
        }}
        [data-testid="metric-container"] [class*="Value"],
        [data-testid="metric-container"] [class*="Value"] p {{
            font-size: 2rem !important;
            font-weight: 700 !important;
            color: {t["text"]} !important;
        }}
        [data-testid="stSidebar"] {{
            border-right: 1px solid {t["border_strong"]};
        }}
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {{ margin-top: -0.4rem; }}
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:first-child {{ margin-top: 0; }}
        [data-testid="stSidebar"] hr {{ display: none; }}
        [data-testid="stSidebar"] button[kind="primary"] {{
            background: {t["card_bg"]} !important;
            border: 1px solid {t["border"]} !important;
        }}
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {{ gap: 0.3rem; }}
        [data-testid="stSidebar"] [data-testid="stMarkdown"] h1 {{
            font-size: 2rem !important;
            text-align: center !important;
            margin-top: -1rem !important;
            padding-top: 0 !important;
        }}
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-baseweb="label"] {{ color: {t["text_muted"]} !important; }}
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] div {{ color: {t["text"]}; }}
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ color: {t["text_muted"]}; }}

        .block-container {{
            padding-top: 2.5rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }}

        details[data-testid="stExpander"] {{
            background: {t["panel_bg"]} !important;
            background-color: {t["panel_bg"]} !important;
            border: 1px solid {t["border_strong"]} !important;
            border-radius: 12px !important;
            --secondary-background-color: {t["panel_bg"]};
        }}
        details[data-testid="stExpander"] summary,
        details[data-testid="stExpander"] summary span,
        details[data-testid="stExpander"] summary p {{
            color: {t["text"]} !important;
            background: transparent !important;
            background-color: transparent !important;
            --secondary-background-color: {t["panel_bg"]};
        }}
        details[data-testid="stExpander"]:hover,
        details[data-testid="stExpander"][open] {{
            background: {t["panel_bg"]} !important;
            border-color: {t["border_strong"]} !important;
        }}
        details[data-testid="stExpander"] summary:hover,
        details[data-testid="stExpander"] summary:focus,
        details[data-testid="stExpander"] summary:active {{
            background: {t["card_bg"]} !important;
            color: {t["text"]} !important;
            outline: none !important;
            border-color: transparent !important;
        }}

        .stButton > button,
        .stDownloadButton > button,
        div[data-testid="stHorizontalBlock"] button {{
            background: {t["card_bg"]} !important;
            border: 1px solid {t["border"]} !important;
            border-radius: 0.75rem !important;
            color: {t["text"]} !important;
        }}
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        div[data-testid="stHorizontalBlock"] button:hover {{
            border-color: {t["border_hover"]} !important;
        }}

        hr {{ border-color: {t["hr"]} !important; }}

        [data-testid="stPlotlyChart"] {{
            background: {t["card_bg"]};
            border-radius: 1rem;
        }}

        [data-testid="stDataFrame"] {{
            border: 1px solid {t["border_strong"]};
            border-radius: 12px;
            overflow: hidden;
        }}

        [data-testid="stAlert"] {{
            background: {t["card_bg"]} !important;
            color: {t["text"]} !important;
            border-color: {t["border"]} !important;
        }}

        [data-baseweb="tab-list"] {{ background: {t["panel_bg"]} !important; }}
        [data-baseweb="tab"] {{ color: {t["text_muted"]} !important; }}
        [data-baseweb="tab"][aria-selected="true"] {{ color: {t["text"]} !important; }}
        [data-baseweb="tab-border"] {{ border-color: {t["border"]} !important; }}
        [data-baseweb="tab-highlight"] {{ background-color: {t["accent"]} !important; }}

        code {{ color: {t["text"]} !important; background: {t["card_bg"]} !important; }}
        pre {{ background: {t["card_bg"]} !important; border: 1px solid {t["border"]} !important; }}
        pre code {{ color: {t["text_cell"]} !important; }}

        [data-testid="stCheckbox"] label,
        [data-testid="stRadio"] label {{ color: {t["text"]} !important; }}

        [data-testid="stDateInput"] [data-baseweb="input"] {{
            background: {t["card_bg"]} !important;
            color: {t["text"]} !important;
        }}

        .stFormSubmitButton > button {{
            background: {t["accent"]} !important;
            color: #fff !important;
            border: none !important;
        }}

        [data-testid="stFileUploaderDropzone"] {{
            background: {t["card_bg"]} !important;
            border: 2px dashed {t["border"]} !important;
            border-radius: 12px !important;
        }}
        [data-testid="stFileUploaderDropzone"]:hover {{
            border-color: {t["border_hover"]} !important;
            background: {t["card_bg"]} !important;
        }}
        [data-testid="stFileUploaderDropzoneInstructions"] {{
            color: {t["text"]} !important;
        }}
        [data-testid="stFileUploaderDropzoneInstructions"] * {{
            color: {t["text"]} !important;
        }}
        [data-testid="stFileUploaderDropzoneInput"] + span button {{
            background: {t["card_bg"]} !important;
            border: 1px solid {t["border"]} !important;
            color: {t["text"]} !important;
        }}
        [data-testid="stFileUploaderDropzoneInput"] + span button:hover {{
            border-color: {t["border_hover"]} !important;
        }}
    </style>
    """




def build_late_theme_override(theme: dict[str, str]) -> str:
    t = theme
    return f"""
    <style>
    [data-theme="dark"] [data-baseweb="popover"],
    [data-baseweb="popover"],
    [data-baseweb="popover"] > div {{
        background: {t["panel_bg"]} !important;
        border-color: {t["border"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"],
    [data-theme="dark"] [data-baseweb="menu"] > div,
    [data-theme="dark"] [data-baseweb="menu"] > ul,
    [data-baseweb="menu"],
    [data-baseweb="menu"] > div,
    [data-baseweb="menu"] > ul {{
        background: {t["panel_bg"]} !important;
    }}
    [data-theme="dark"] [role="option"],
    [data-theme="dark"] [role="listbox"] > div,
    [role="option"],
    [role="listbox"] > div {{
        background: {t["panel_bg"]} !important;
        color: {t["text"]} !important;
    }}
    [data-theme="dark"] [role="option"]:hover,
    [data-theme="dark"] [role="listbox"] > div:hover,
    [role="option"]:hover,
    [role="listbox"] > div:hover {{
        background: {t["card_bg"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"] [role="option"],
    [data-baseweb="menu"] [role="option"] {{
        background-color: {t["panel_bg"]} !important;
        color: {t["text"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"] [role="option"]:hover,
    [data-baseweb="menu"] [role="option"]:hover,
    [data-theme="dark"] [role="option"]:focus,
    [data-theme="dark"] [role="option"]:active,
    [data-theme="dark"] [role="option"][aria-selected="true"],
    [role="option"]:focus,
    [role="option"]:active,
    [role="option"][aria-selected="true"] {{
        background-color: {t["card_bg"]} !important;
        color: {t["text"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="option"],
    [data-baseweb="option"] {{
        background-color: {t["panel_bg"]} !important;
        color: {t["text"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="option"]:hover,
    [data-theme="dark"] [data-baseweb="option"]:focus,
    [data-theme="dark"] [data-baseweb="option"]:active,
    [data-baseweb="option"]:hover,
    [data-baseweb="option"]:focus,
    [data-baseweb="option"]:active {{
        background-color: {t["card_bg"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"] li[aria-selected],
    [data-baseweb="menu"] li[aria-selected] {{
        background-color: {t["card_bg"]} !important;
        color: {t["text"]} !important;
    }}
    [data-theme="dark"] [data-baseweb="menu"] li[aria-selected]:focus,
    [data-theme="dark"] [data-baseweb="menu"] li[aria-selected]:hover,
    [data-baseweb="menu"] li[aria-selected]:focus,
    [data-baseweb="menu"] li[aria-selected]:hover {{
        background-color: {t["card_bg"]} !important;
    }}
    :root,
    [data-theme="dark"] {{
        --SDS-colorBackground-body: {t["page_bg"]};
        --SDS-colorBackground-iteration0: {t["panel_bg"]};
        --SDS-colorBackground-constructionRotation0: {t["card_bg"]};
        --SDS-colorBase-positive: {t["accent"]};
        --secondary-background-color: {t["panel_bg"]};
    }}
    details[data-testid="stExpander"] {{
        background-color: {t["panel_bg"]} !important;
        border-color: {t["border_strong"]} !important;
    }}
    details[data-testid="stExpander"] summary {{
        background-color: {t["panel_bg"]} !important;
        color: {t["text"]} !important;
    }}
    details[data-testid="stExpander"] summary * {{
        background-color: transparent !important;
        color: {t["text"]} !important;
    }}
    details[data-testid="stExpander"] summary:hover,
    details[data-testid="stExpander"] summary:focus,
    details[data-testid="stExpander"] summary:active {{
        background-color: {t["card_bg"]} !important;
        outline: none !important;
    }}
    [role="dialog"],
    [data-testid="stDialog"],
    [role="dialog"] > div,
    [data-testid="stDialog"] > div,
    [role="dialog"] [data-testid="stVerticalBlock"],
    [data-testid="stDialog"] [data-testid="stVerticalBlock"] {{
        background-color: {t["panel_bg"]} !important;
    }}
    [role="dialog"],
    [data-testid="stDialog"],
    [role="dialog"] > div,
    [data-testid="stDialog"] > div {{
        border: 1px solid {t["border_strong"]} !important;
    }}
    [role="dialog"] button[aria-label="Close"],
    [data-testid="stDialog"] button[aria-label="Close"] {{
        color: {t["text"]} !important;
        background-color: transparent !important;
    }}
    [role="dialog"] button[aria-label="Close"]:hover,
    [data-testid="stDialog"] button[aria-label="Close"]:hover {{
        background-color: {t["card_bg"]} !important;
    }}
    [data-baseweb="tooltip"],
    .stTooltipContent {{
        background-color: {t["panel_bg"]} !important;
        color: {t["text"]} !important;
        border: 1px solid {t["border_strong"]} !important;
        --colorBackgroundTooltip: {t["panel_bg"]};
    }}
    [data-baseweb="tooltip"] *,
    [data-baseweb="tooltip"] div {{
        background-color: {t["panel_bg"]} !important;
        color: {t["text"]} !important;
    }}
    </style>
    """




def build_streamlit_fix_script(theme: dict[str, str]) -> str:
    t = theme
    css = (
        '[data-testid="stExpander"]{' +
        'background-color:%s !important;' +
        'border-color:%s !important;' +
        '}' +
        '[data-testid="stExpander"] summary{' +
        'background-color:%s !important;' +
        'color:%s !important;' +
        '}' +
        '[data-testid="stExpander"] summary *{' +
        'background-color:transparent !important;' +
        'color:%s !important;' +
        '}' +
        '[data-testid="stExpander"] summary:hover,' +
        '[data-testid="stExpander"] summary:focus,' +
        '[data-testid="stExpander"] summary:active{' +
        'background-color:%s !important;' +
        'outline:none !important;' +
        '}' +
        '.st-fh{color:%s !important;}'
    ) % (t["panel_bg"], t["border_strong"], t["panel_bg"], t["text"], t["text"], t["card_bg"], t["text"])
    return (
        "<script>\n"
        "(function() {\n"
        "    var doc;\n"
        "    try { doc = window.parent.document; } catch(e) { doc = document; }\n"
        "    function injectExpanderFix() {\n"
        "        var id = 'negotium-expander-fix';\n"
        "        var existing = doc.getElementById(id);\n"
        "        if (existing) existing.parentNode.removeChild(existing);\n"
        "        var s = doc.createElement('style');\n"
        "        s.id = id;\n"
        "        s.innerHTML = " + repr(css) + ";\n"
        "        doc.head.appendChild(s);\n"
        "        function fixPlaceholderColors() {\n"
        "            var muted = 'rgba(241, 245, 249, 0.6)';\n"
        "            var selects = doc.querySelectorAll('[data-baseweb=\"select\"]');\n"
        "            for (var i = 0; i < selects.length; i++) {\n"
        "                var divs = selects[i].querySelectorAll('div');\n"
        "                for (var j = 0; j < divs.length; j++) {\n"
        "                    var st = (doc.defaultView || window).getComputedStyle(divs[j]);\n"
        "                    if (st.color === muted && divs[j].textContent.trim() !== '') {\n"
        "                        divs[j].style.color = '" + t["text"] + "';\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        fixPlaceholderColors();\n"
        "        setTimeout(fixPlaceholderColors, 300);\n"
        "    }\n"
        "    injectExpanderFix();\n"
        "    setTimeout(injectExpanderFix, 300);\n"
        "})();\n"
        "</script>\n"
    )



# Component styles


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


__all__ = [
    "build_app_styles",
    "build_late_theme_override",
    "build_streamlit_fix_script",
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
]
