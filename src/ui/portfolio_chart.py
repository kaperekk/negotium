from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_portfolio_chart(T: dict[str, str], base_ccy: str, dates, values, investeds,
                          bench_by_date: dict[str, dict], BENCHMARKS: dict[str, str],
                          BENCH_COLORS: dict[str, str], chart_mode: str) -> None:
    SYM = {"PLN": " PLN", "EUR": "€", "USD": "$"}

    fig = go.Figure()

    if chart_mode == "amount":
        fig.add_trace(go.Scatter(
            x=dates, y=[round(v, 2) for v in values],
            name=f"Portfolio ({base_ccy})",
            fill="tozeroy",
            line=dict(color="#6C63FF", width=2.5),
            fillcolor="rgba(108,99,255,0.08)",
            customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in values],
            hovertemplate="%{customdata}<extra>Portfolio</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=dates, y=[round(v, 2) for v in investeds],
            name="Invested",
            line=dict(color="#94a3b8", width=1.5, dash="dot"),
            customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in investeds],
            hovertemplate="%{customdata}<extra>Invested</extra>",
        ))
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=False, tickfont=dict(size=20, color=T["text_muted"]), tickformat=",.2f",
            ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
            tickprefix="" if base_ccy == "PLN" else SYM[base_ccy],
            title=dict(font=dict(size=18, color=T["text_muted"]))
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
            line=dict(color="#6C63FF", width=2.5),
            fillcolor="rgba(108,99,255,0.08)",
            hovertemplate="%{y:+.2f}%<extra>Return</extra>",
        ))
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=True, zerolinecolor=T["chart_zeroline"],
            tickfont=dict(size=20, color=T["text_muted"]),
            ticksuffix="%",
            tickformat="+.1f",
            title=dict(font=dict(size=18, color=T["text_muted"]))
        )

    bench_selected = {
        label: label in st.session_state.get("bench_persist", [])
        for label in BENCHMARKS
    }

    for bench_label, bench_ticker in BENCHMARKS.items():
        if not bench_selected.get(bench_label):
            continue

        bench_vals = [bench_by_date.get(d, {}).get(bench_ticker, 0.0) for d in dates]
        if chart_mode == "percent":
            bench_pcts = [
                round(((bv / inv) - 1.0) * 100.0, 2) if inv else 0.0
                for bv, inv in zip(bench_vals, investeds)
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=bench_pcts,
                name=bench_label,
                line=dict(color=BENCH_COLORS[bench_label], width=1.5, dash="dot"),
                hovertemplate="%{y:+.2f}%<extra>" + bench_label + "</extra>",
            ))
        else:
            fig.add_trace(go.Scatter(
                x=dates, y=bench_vals,
                name=bench_label,
                line=dict(color=BENCH_COLORS[bench_label], width=1.5, dash="dot"),
                customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in bench_vals],
                hovertemplate="%{customdata}<extra>" + bench_label + "</extra>",
            ))

    if chart_mode == "amount":
        ys = [v for tr in fig.data if tr.y is not None for v in tr.y if v is not None]
        if ys:
            fig.update_yaxes(range=[min(ys) * 0.98, max(ys) * 1.02])
    else:
        pct_values = [v for tr in fig.data if tr.name == "Return (%)" for v in tr.y if v is not None]
        if pct_values:
            span = max(abs(min(pct_values)), abs(max(pct_values))) if pct_values else 1
            fig.update_yaxes(range=[-span * 1.15, span * 1.15])

    fig.update_layout(
        template=T["plotly_template"],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=T["hover_bg"],
            bordercolor=T["border_strong"],
            font=dict(size=18, color=T["text"], family="sans-serif"),
            namelength=-1,
        ),
        font=dict(family="sans-serif", size=20),
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=16, color=T["text_muted"]),
            title=dict(font=dict(size=18, color=T["text_muted"])),
        ),
        yaxis=yaxis_cfg,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
