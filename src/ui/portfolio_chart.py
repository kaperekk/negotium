from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
from ui.colors import (
    ACCENT,
    ACCENT_FILL,
    MUTED_LINE,
)
from ui.sizes import (
    HOVER_LABEL_SIZE,
    AXIS_TICK_FONT_SIZE,
    AXIS_TITLE_FONT_SIZE,
    CHART_HEIGHT_PORTFOLIO,
    PORTFOLIO_TICK_FONT,
    PORTFOLIO_TITLE_FONT,
    PORTFOLIO_GLOBAL_FONT,
)


def render_portfolio_chart(T: dict[str, str], base_ccy: str, dates, values, investeds,
                           bench_by_date: dict[str, dict], BENCHMARKS: dict[str, str],
                           BENCH_COLORS: dict[str, str], chart_mode: str,
                           log_scale: bool = False) -> None:
    SYM = {"PLN": " PLN", "EUR": "€", "USD": "$"}

    fig = go.Figure()
    is_log = bool(log_scale)

    if chart_mode == "amount":
        fig.add_trace(go.Scatter(
            x=dates, y=[round(v, 2) for v in values],
            name=f"Portfolio ({base_ccy})",
            fill="tozeroy",
            line=dict(color=ACCENT, width=2.5),
            fillcolor=ACCENT_FILL,
            customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in values],
            hovertemplate="%{customdata}<extra>Portfolio</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=dates, y=[round(v, 2) for v in investeds],
            name="Invested",
            line=dict(color=MUTED_LINE, width=1.5, dash="dot"),
            customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in investeds],
            hovertemplate="%{customdata}<extra>Invested</extra>",
        ))
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=False, tickfont=dict(size=PORTFOLIO_TICK_FONT, color=T["text_muted"]), tickformat=",.2f",
            ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
            tickprefix="" if base_ccy == "PLN" else SYM[base_ccy],
            title=dict(font=dict(size=PORTFOLIO_TITLE_FONT, color=T["text_muted"])),
            type="log" if is_log else "linear",
        )
    elif chart_mode == "profit":
        pnl_series = [round(v - inv, 2) for v, inv in zip(values, investeds)]
        fig.add_trace(go.Scatter(
            x=dates, y=pnl_series,
            name=f"Profit ({base_ccy})",
            fill="tozeroy",
            line=dict(color=ACCENT, width=2.5),
            fillcolor=ACCENT_FILL,
            customdata=[f"{v:+,.2f}".replace(",", " ") + f" {base_ccy}" for v in pnl_series],
            hovertemplate="%{customdata}<extra>Profit</extra>",
        ))
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=True, zerolinecolor=T["chart_zeroline"],
            tickfont=dict(size=PORTFOLIO_TICK_FONT, color=T["text_muted"]), tickformat=",.2f",
            ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
            tickprefix="" if base_ccy == "PLN" else SYM[base_ccy],
            title=dict(font=dict(size=PORTFOLIO_TITLE_FONT, color=T["text_muted"])),
            type="log" if is_log else "linear",
        )

    else:
        pct_values = [
            round(((v / inv) - 1.0) * 100.0, 2) if inv else 0.0
            for v, inv in zip(values, investeds)
        ]
        fig.add_trace(go.Scatter(
            x=dates, y=pct_values,
            name="Return (%)",
            fill="tozeroy",
            line=dict(color=ACCENT, width=2.5),
            fillcolor=ACCENT_FILL,
            hovertemplate="%{y:+.2f}%<extra>Return</extra>",
        ))
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=True, zerolinecolor=T["chart_zeroline"],
            tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            ticksuffix="%",
            tickformat="+.1f",
            title=dict(font=dict(size=AXIS_TITLE_FONT_SIZE, color=T["text_muted"])),
            type="log" if is_log else "linear",
        )

    bench_selected = {
        label: label in st.session_state.get("bench_persist", [])
        for label in BENCHMARKS
    }

    for bench_label, bench_ticker in BENCHMARKS.items():
        if not bench_selected.get(bench_label):
            continue

        bench_vals = [bench_by_date.get(d, {}).get(bench_ticker, 0.0) for d in dates]
        # Benchmarks launched after the portfolio's first transaction carry
        # leading 0.0 placeholders (no price yet). Render them as gaps so the
        # line starts at its first real value instead of hugging zero (amount
        # mode) or diving to -100% (percent mode) and skewing the axis range.
        first = next((i for i, v in enumerate(bench_vals) if v), None)
        if first:
            bench_vals = [None] * first + bench_vals[first:]

        if chart_mode == "percent":
            bench_pcts = [
                round(((bv / inv) - 1.0) * 100.0, 2)
                if (bv is not None and inv) else None
                for bv, inv in zip(bench_vals, investeds)
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=bench_pcts,
                name=bench_label,
                line=dict(color=BENCH_COLORS[bench_label], width=1.5, dash="dot"),
                connectgaps=False,
                hovertemplate="%{y:+.2f}%<extra>" + bench_label + "</extra>",
            ))
        elif chart_mode == "profit":
            bench_pnl = [
                round(bv - inv, 2) if bv is not None else None
                for bv, inv in zip(bench_vals, investeds)
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=bench_pnl,
                name=bench_label,
                line=dict(color=BENCH_COLORS[bench_label], width=1.5, dash="dot"),
                connectgaps=False,
                customdata=[
                    f"{v:+,.2f}".replace(",", " ") + f" {base_ccy}" if v is not None else ""
                    for v in bench_pnl
                ],
                hovertemplate="%{customdata}<extra>" + bench_label + "</extra>",
            ))
        else:
            fig.add_trace(go.Scatter(
                x=dates, y=bench_vals,
                name=bench_label,
                line=dict(color=BENCH_COLORS[bench_label], width=1.5, dash="dot"),
                connectgaps=False,
                customdata=[
                    f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" if v is not None else ""
                    for v in bench_vals
                ],
                hovertemplate="%{customdata}<extra>" + bench_label + "</extra>",
            ))

    if chart_mode == "amount":
        ys = [v for tr in fig.data if tr.y is not None for v in tr.y if v is not None]
        if ys:
            if is_log:
                pos_ys = [v for v in ys if v > 0]
                if pos_ys:
                    import math
                    min_val = min(pos_ys) * 0.98
                    max_val = max(pos_ys) * 1.02
                    fig.update_yaxes(type="log", range=[math.log10(max(min_val, 1e-4)), math.log10(max_val)])
            else:
                fig.update_yaxes(range=[min(ys) * 0.98, max(ys) * 1.02])
    elif chart_mode == "profit":
        ys = [v for tr in fig.data if tr.y is not None for v in tr.y if v is not None]
        if ys:
            if is_log:
                pos_ys = [v for v in ys if v > 0]
                if pos_ys:
                    import math
                    min_val = min(pos_ys) * 0.98
                    max_val = max(pos_ys) * 1.02
                    fig.update_yaxes(type="log", range=[math.log10(max(min_val, 1e-4)), math.log10(max_val)])
            else:
                # Keep the breakeven line (0) in view; 5% headroom on each side.
                lo, hi = min(min(ys), 0.0), max(max(ys), 0.0)
                pad = max((hi - lo) * 0.05, 1.0)
                fig.update_yaxes(range=[lo - pad, hi + pad])
    else:
        # Include every percent-mode trace (portfolio return + benchmark
        # overlays) — otherwise a benchmark outperforming the portfolio is
        # clipped instead of zooming the axis out. Fit the data directly with
        # 5% headroom on each side (not zero-centred symmetric).
        pct_values = [v for tr in fig.data if tr.y is not None for v in tr.y if v is not None]
        if pct_values:
            if is_log:
                pos_pcts = [v for v in pct_values if v > 0]
                if pos_pcts:
                    import math
                    min_val = min(pos_pcts) * 0.98
                    max_val = max(pos_pcts) * 1.02
                    fig.update_yaxes(type="log", range=[math.log10(max(min_val, 1e-4)), math.log10(max_val)])
            else:
                lo, hi = min(pct_values), max(pct_values)
                pad = max((hi - lo) * 0.05, 1.0)  # ≥1pp floor keeps flat series readable
                fig.update_yaxes(range=[lo - pad, hi + pad])

    fig.update_layout(
        template=T["plotly_template"],
        paper_bgcolor=T["chart_bg"],
        plot_bgcolor=T["chart_bg"],
        margin=dict(l=10, r=10, t=10, b=10),
        height=CHART_HEIGHT_PORTFOLIO,
        legend=dict(orientation="h", yanchor="top", y=0.98, xanchor="left", x=0.01, font=dict(color=T["text"])),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=T["hover_bg"],
            bordercolor=T["border_strong"],
            font=dict(size=HOVER_LABEL_SIZE, color=T["hover_text"], family="sans-serif"),
            namelength=-1,
        ),
        font=dict(family="sans-serif", size=PORTFOLIO_GLOBAL_FONT, color=T["text"]),
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            title=dict(font=dict(size=AXIS_TITLE_FONT_SIZE, color=T["text_muted"])),
        ),
        yaxis=yaxis_cfg,
    )
    st.plotly_chart(fig, width="stretch", key="portfolio_main", config={"displayModeBar": False})
