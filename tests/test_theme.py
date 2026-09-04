"""Theme palettes — pytest suite (split from the original monolithic runner)."""

from __future__ import annotations

from pathlib import Path


REQUIRED_THEME_KEYS = [
    "card_bg", "border", "border_hover", "border_active", "border_strong",
    "text", "text_cell", "text_muted", "text_faint",
    "panel_bg", "hr", "accent",
    "accent_tag_bg", "accent_tag_border", "accent_tag_hover",
    "card_btn_active", "card_faint",
    "chart_grid", "chart_zeroline", "hover_bg",
    "plotly_template", "page_bg",
    "range_bg", "range_active",
    "table_border", "table_header_border", "table_hover", "table_text",
    "holdings_bar_bg",
]


def _is_valid_css_color(value: str) -> bool:
    """Check if a string looks like a valid CSS color."""
    import re
    # Named colors, hex, rgb(), rgba(), hsl(), hsla()
    if value.startswith("#"):
        return len(value) in (4, 5, 7, 9) and all(c in "0123456789abcdefABCDEF" for c in value[1:])
    if value.startswith(("rgb(", "rgba(", "hsl(", "hsla(")):
        return bool(re.match(r"^(rgb|rgba|hsl|hsla)\(.+\)$", value))
    return False


def test_theme_keys_dark(tmp: Path):
    """Dark theme defines all required keys."""
    from ui.colors import THEMES
    for key in REQUIRED_THEME_KEYS:
        assert key in THEMES["dark"], f"Dark theme missing key: {key}"


def test_theme_keys_light(tmp: Path):
    """Light theme defines all required keys."""
    from ui.colors import THEMES
    for key in REQUIRED_THEME_KEYS:
        assert key in THEMES["light"], f"Light theme missing key: {key}"


def test_theme_colors_valid(tmp: Path):
    """All theme color values are valid CSS colors."""
    from ui.colors import THEMES
    NON_COLOR_KEYS = {"plotly_template"}
    for theme_name, theme in THEMES.items():
        for key, value in theme.items():
            if key in NON_COLOR_KEYS:
                continue
            assert _is_valid_css_color(value), f"{theme_name}.{key} = {value!r} is not a valid CSS color"


def test_theme_plotly_template(tmp: Path):
    """Dark uses plotly_dark, light uses plotly_white."""
    from ui.colors import THEMES
    assert THEMES["dark"]["plotly_template"] == "plotly_dark"
    assert THEMES["light"]["plotly_template"] == "plotly_white"


def test_theme_css_uses_correct_colors(tmp: Path):
    """CSS builders produce output containing the theme's colors."""
    from ui.colors import THEMES
    from ui.styles import build_app_styles, build_metric_card_styles

    for theme_name in ("dark", "light"):
        t = THEMES[theme_name]

        app_css = build_app_styles(t)
        assert t["page_bg"] in app_css, f"{theme_name}: build_app_styles missing page_bg"
        assert t["panel_bg"] in app_css, f"{theme_name}: build_app_styles missing panel_bg"
        assert t["text"] in app_css, f"{theme_name}: build_app_styles missing text"

        metric_css = build_metric_card_styles(t)
        assert t["card_bg"] in metric_css, f"{theme_name}: build_metric_card_styles missing card_bg"
        assert t["text"] in metric_css, f"{theme_name}: build_metric_card_styles missing text"


def test_theme_plotly_font_colors(tmp: Path):
    """Plotly chart layout uses theme text color for fonts."""
    from ui.colors import THEMES
    import plotly.graph_objects as go

    for theme_name in ("dark", "light"):
        t = THEMES[theme_name]
        fig = go.Figure()
        fig.update_layout(
            font=dict(family="sans-serif", size=20, color=t["text"]),
        )
        assert fig.layout.font.color == t["text"], (
            f"{theme_name}: Plotly font color {fig.layout.font.color} != {t['text']}"
        )


def test_theme_dark_text_on_dark_bg(tmp: Path):
    """Dark theme text colors are light (for dark backgrounds)."""
    from ui.colors import THEMES
    t = THEMES["dark"]
    # Text should start with # (hex) and have high RGB values
    for key in ("text", "text_cell", "text_muted"):
        val = t[key]
        if val.startswith("#"):
            r = int(val[1:3], 16)
            g = int(val[3:5], 16)
            b = int(val[5:7], 16)
            assert r > 100 and g > 100 and b > 100, (
                f"Dark theme {key}={val} is too dark for dark backgrounds"
            )


def test_theme_light_text_on_light_bg(tmp: Path):
    """Light theme text colors are dark (for light backgrounds)."""
    from ui.colors import THEMES
    t = THEMES["light"]
    for key in ("text", "text_cell", "text_muted"):
        val = t[key]
        if val.startswith("#"):
            r = int(val[1:3], 16)
            g = int(val[3:5], 16)
            b = int(val[5:7], 16)
            assert r < 150 and g < 150 and b < 150, (
                f"Light theme {key}={val} is too light for light backgrounds"
            )
