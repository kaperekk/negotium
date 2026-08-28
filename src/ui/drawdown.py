"""
drawdown.py — Drawdown Analysis section

Computes peak-to-trough drawdown statistics from the portfolio value series
and renders them as metric cards plus an "underwater" chart.
"""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
import streamlit as st
from ui.colors import (
    ACCENT,
    AXIS_TICK_FONT_SIZE,
    AXIS_TITLE_FONT_SIZE,
    HOVER_LABEL_SIZE,
)


def _hex_rgba(hex_color: str, alpha: float) -> str:
    """Convert '#RRGGBB' to an rgba() string with the given alpha."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _compute_drawdown_metrics(snapshots) -> dict | None:
    dates = [s["date"] for s in snapshots]
    vals = [float(s.get("total_value", 0.0)) for s in snapshots]
    if len(vals) < 2 or all(v <= 0 for v in vals):
        return None

    peak: list[float] = []
    running = vals[0]
    for v in vals:
        running = max(running, v)
        peak.append(running)

    dd = [(v / p - 1.0) if p > 0 else 0.0 for v, p in zip(vals, peak)]

    max_dd = min(dd)
    cur_dd = dd[-1]

    # Drawdown episodes (peak → trough → recovery)
    in_dd = False
    ep_start = 0
    longest_dur = 0
    for i, d in enumerate(dd):
        if d < 0 and not in_dd:
            in_dd = True
            ep_start = i
        elif d >= 0 and in_dd:
            in_dd = False
            dur = (date.fromisoformat(dates[i]) - date.fromisoformat(dates[ep_start])).days
            longest_dur = max(longest_dur, dur)

    if in_dd:
        cur_dd_dur = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[ep_start])).days
        longest_dur = max(longest_dur, cur_dd_dur)
    else:
        cur_dd_dur = 0

    ulcer = (sum(d * d for d in dd) / len(dd)) ** 0.5  # fraction

    days_total = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
    cagr = 0.0
    if days_total > 0 and vals[0] > 0:
        cagr = (vals[-1] / vals[0]) ** (365.0 / days_total) - 1.0
    pain = (cagr / ulcer) if ulcer > 0 else None

    return {
        "max_dd": max_dd,
        "cur_dd": cur_dd,
        "longest_dur": longest_dur,
        "cur_dd_dur": cur_dd_dur,
        "ulcer": ulcer,
        "pain": pain,
        "dates": dates,
        "dd": dd,
    }


def render_drawdown_analysis(snapshots, T: dict) -> None:
    m = _compute_drawdown_metrics(snapshots)
    if m is None:
        st.caption("Not enough data for drawdown analysis.")
        return

    def pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    st.subheader("📉  Drawdown Analysis")

    c1, c2, c3 = st.columns(3)
    c1.metric("Max drawdown", pct(m["max_dd"]),
              help="Largest peak-to-trough decline over the whole period.")
    c2.metric("Current drawdown", pct(m["cur_dd"]),
              help="How far today's value is below the previous all-time high.")
    c3.metric("Ulcer Index", pct(m["ulcer"]),
              help="Root-mean-square of all daily drawdowns — penalises long, deep declines.")

    c4, c5, c6 = st.columns(3)
    c4.metric("Longest drawdown", f"{m['longest_dur']} d",
              help="Most days spent underwater before recovering to a new high.")
    c5.metric("Current DD duration", f"{m['cur_dd_dur']} d" if m["cur_dd_dur"] else "—",
              help="Days since the last peak (0 / — if currently at a new high).")
    c6.metric("Pain Ratio", f"{m['pain']:.2f}×" if m["pain"] is not None else "—",
              help="Annualised return ÷ Ulcer Index. Higher = better return per unit of downside.")

    st.caption(
        "Underwater chart: how far the portfolio has fallen below its previous high. "
        "0% = at a new high; deeper red = bigger loss from peak."
    )

    dd_pct = [d * 100 for d in m["dd"]]
    worst_i = int(min(range(len(dd_pct)), key=lambda i: dd_pct[i]))

    theme_name = st.session_state.get("theme", "dark")
    is_light = theme_name == "light"
    if is_light:
        txt = "#1F2328"
        grid = "rgba(200,205,212,0.5)"
        zero = "rgba(200,205,212,0.7)"
    else:
        txt = "#E6EDF3"
        grid = "rgba(48,54,61,0.6)"
        zero = "rgba(48,54,61,0.8)"

    accent = T.get("accent", ACCENT)
    accent_fill = _hex_rgba(accent, 0.25)

    fig = go.Figure(
        go.Scatter(
            x=m["dates"],
            y=dd_pct,
            fill="tozeroy",
            fillcolor=accent_fill,
            line=dict(color=accent, width=1),
            hovertemplate="%{x}<br>Drawdown: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_hline(y=0, line=dict(color=zero, width=1, dash="dot"))
    fig.add_annotation(
        x=m["dates"][worst_i],
        y=dd_pct[worst_i],
        text=f"Max {pct(m['max_dd'])}",
        showarrow=True,
        arrowhead=2,
        font=dict(color=accent, size=22),
        yshift=-10,
    )
    fig.update_layout(
        template="plotly_white" if is_light else "plotly_dark",
        height=420,
        margin=dict(t=20, b=10, l=10, r=10),
        paper_bgcolor=T["chart_bg"],
        plot_bgcolor=T["chart_bg"],
        font=dict(color=txt, size=24),
        yaxis=dict(
            title=dict(text="Drawdown from peak (%)", font=dict(color=txt, size=AXIS_TITLE_FONT_SIZE)),
            tickfont=dict(color=txt, size=AXIS_TICK_FONT_SIZE),
            gridcolor=grid,
            zerolinecolor=zero,
            linecolor=zero,
        ),
        xaxis=dict(showgrid=False, linecolor=zero, tickfont=dict(color=txt, size=AXIS_TICK_FONT_SIZE)),
        hoverlabel=dict(font=dict(size=HOVER_LABEL_SIZE, color=T["hover_text"])),
    )
    st.plotly_chart(fig, use_container_width=True)
