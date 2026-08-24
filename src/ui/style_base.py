"""Base application styling and runtime CSS overrides."""

from __future__ import annotations


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
            min-width: 380px;
            max-width: 420px;
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
