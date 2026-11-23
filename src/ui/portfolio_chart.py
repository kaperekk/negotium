from __future__ import annotations

import math
from datetime import date
import plotly.graph_objects as go
import streamlit as st

from ticker_data import get_price
from ui.colors import (
    ACCENT,
    ACCENT_FILL,
    MUTED_LINE,
    NEGATIVE,
    POSITIVE,
    BENCHMARKS,
    BENCH_COLORS,
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


def render_portfolio_chart(
    T: dict[str, str],
    base_ccy: str,
    snapshots: list[dict],
    bench_by_date: dict[str, dict],
    benchmarks: dict[str, str],
    bench_colors: dict[str, str],
    chart_mode: str = "value",
    log_scale: bool = False,
) -> None:
    """Render the primary unified portfolio chart supporting 5 metric modes."""
    if not snapshots:
        st.warning("Brak danych portfela dla wybranego zakresu.")
        return

    dates = [s["date"] for s in snapshots]
    values = [float(s.get("total_value", 0.0)) for s in snapshots]
    investeds = [float(s.get("invested", 0.0)) for s in snapshots]

    SYM = {"PLN": " zł", "EUR": " €", "USD": " $"}
    fig = go.Figure()
    is_log = bool(log_scale)

    # Normalize chart_mode
    mode = chart_mode.lower()
    if mode in ("amount", "value", "wartość portfela"):
        mode = "value"
    elif mode in ("profit", "zysk", "zysk całkowity"):
        mode = "profit"
    elif mode in ("twr", "wynik portfela"):
        mode = "twr"
    elif mode in ("mwr", "percent", "zwrot inwestora"):
        mode = "mwr"
    elif mode in ("drawdown", "obsunięcie"):
        mode = "drawdown"

    if mode == "value":
        fig.add_trace(go.Scatter(
            x=dates, y=[round(v, 2) for v in values],
            name=f"Portfel ({base_ccy})",
            fill="tozeroy",
            line=dict(color=ACCENT, width=2.5),
            fillcolor=ACCENT_FILL,
            customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in values],
            hovertemplate="%{customdata}<extra>Wartość portfela</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=dates, y=[round(v, 2) for v in investeds],
            name="Wpłacony kapitał",
            line=dict(color=MUTED_LINE, width=1.5, dash="dot"),
            customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in investeds],
            hovertemplate="%{customdata}<extra>Wpłacony kapitał</extra>",
        ))
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=False, tickfont=dict(size=PORTFOLIO_TICK_FONT, color=T["text_muted"]), tickformat=",.0f",
            ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
            tickprefix="" if base_ccy == "PLN" else SYM.get(base_ccy, ""),
            title=dict(font=dict(size=PORTFOLIO_TITLE_FONT, color=T["text_muted"])),
            type="log" if is_log else "linear",
        )

    elif mode == "profit":
        pnl_series = [round(float(s.get("pnl", v - inv)), 2) for s, v, inv in zip(snapshots, values, investeds)]
        fig.add_trace(go.Scatter(
            x=dates, y=pnl_series,
            name=f"Zysk całkowity ({base_ccy})",
            fill="tozeroy",
            line=dict(color=ACCENT, width=2.5),
            fillcolor=ACCENT_FILL,
            customdata=[f"{v:+,.2f}".replace(",", " ") + f" {base_ccy}" for v in pnl_series],
            hovertemplate="%{customdata}<extra>Zysk całkowity</extra>",
        ))
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=True, zerolinecolor=T["chart_zeroline"],
            tickfont=dict(size=PORTFOLIO_TICK_FONT, color=T["text_muted"]), tickformat=",.0f",
            ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
            tickprefix="" if base_ccy == "PLN" else SYM.get(base_ccy, ""),
            title=dict(font=dict(size=PORTFOLIO_TITLE_FONT, color=T["text_muted"])),
            type="log" if is_log else "linear",
        )

    elif mode == "twr":
        # Sliced cumulative TWR relative to start of selected window
        twr_0 = float(snapshots[0].get("twr", 0.0))
        twr_series = [
            round(((1.0 + float(s.get("twr", 0.0))) / (1.0 + twr_0) - 1.0) * 100.0, 2)
            if (1.0 + twr_0) > 1e-9 else 0.0
            for s in snapshots
        ]
        fig.add_trace(go.Scatter(
            x=dates, y=twr_series,
            name="TWR (%)",
            fill="tozeroy",
            line=dict(color=ACCENT, width=2.5),
            fillcolor=ACCENT_FILL,
            hovertemplate="%{y:+.2f}%<extra>TWR</extra>",
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

    elif mode == "mwr":
        # Sliced cumulative MWR / simple return % relative to window
        mwr_0 = float(snapshots[0].get("mwr", 0.0))
        mwr_series = [
            round(((1.0 + float(s.get("mwr", 0.0))) / (1.0 + mwr_0) - 1.0) * 100.0, 2)
            if (1.0 + mwr_0) > 1e-9 else 0.0
            for s in snapshots
        ]
        fig.add_trace(go.Scatter(
            x=dates, y=mwr_series,
            name="Zwrot inwestora MWR (%)",
            fill="tozeroy",
            line=dict(color=ACCENT, width=2.5),
            fillcolor=ACCENT_FILL,
            hovertemplate="%{y:+.2f}%<extra>MWR</extra>",
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

    else:  # mode == "drawdown"
        # Drawdown relative to the running peak in this slice
        running_peak = 0.0
        dd_series = []
        for v in values:
            running_peak = max(running_peak, v)
            dd = ((v - running_peak) / running_peak * 100.0) if running_peak > 1e-9 else 0.0
            dd_series.append(round(dd, 2))

        fig.add_trace(go.Scatter(
            x=dates, y=dd_series,
            name="Obsunięcie (%)",
            fill="tozeroy",
            line=dict(color=NEGATIVE, width=2.0),
            fillcolor="rgba(239,68,68,0.12)",
            hovertemplate="%{y:.2f}%<extra>Obsunięcie</extra>",
        ))
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=True, zerolinecolor=T["chart_zeroline"],
            tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            ticksuffix="%",
            tickformat="+.1f",
            title=dict(font=dict(size=AXIS_TITLE_FONT_SIZE, color=T["text_muted"])),
            type="linear",
        )

    # Benchmark overlays when active in main chart
    bench_selected = {
        label: label in st.session_state.get("bench_persist", [])
        for label in benchmarks
    }

    for bench_label, bench_ticker in benchmarks.items():
        if not bench_selected.get(bench_label):
            continue

        bench_vals = [bench_by_date.get(d, {}).get(bench_ticker, 0.0) for d in dates]
        first_idx = next((i for i, v in enumerate(bench_vals) if v and v > 0), None)
        if first_idx is not None:
            bench_vals = [None] * first_idx + bench_vals[first_idx:]
            base_bval = bench_vals[first_idx]
        else:
            base_bval = None

        if mode in ("twr", "mwr"):
            p_cache: dict = {}
            p_raw = [get_price(bench_ticker, d, p_cache, int(d[:4]), adjusted=True) for d in dates]
            last_p = None
            p_filled = []
            for p in p_raw:
                if p is not None and p > 0:
                    last_p = p
                p_filled.append(last_p)

            p0 = next((p for p in p_filled if p is not None and p > 0), None)
            if p0 and p0 > 0:
                bench_pcts = [
                    round(((p / p0) - 1.0) * 100.0, 2) if p is not None else None
                    for p in p_filled
                ]
            else:
                bench_pcts = []

            fig.add_trace(go.Scatter(
                x=dates, y=bench_pcts,
                name=bench_label,
                line=dict(color=bench_colors.get(bench_label, MUTED_LINE), width=1.5, dash="dot"),
                connectgaps=False,
                hovertemplate="%{y:+.2f}%<extra>" + bench_label + "</extra>",
            ))
        elif mode == "profit":
            bench_pnl = [
                round(bv - inv, 2) if bv is not None else None
                for bv, inv in zip(bench_vals, investeds)
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=bench_pnl,
                name=bench_label,
                line=dict(color=bench_colors.get(bench_label, MUTED_LINE), width=1.5, dash="dot"),
                connectgaps=False,
                customdata=[
                    f"{v:+,.2f}".replace(",", " ") + f" {base_ccy}" if v is not None else ""
                    for v in bench_pnl
                ],
                hovertemplate="%{customdata}<extra>" + bench_label + "</extra>",
            ))
        elif mode == "value":
            fig.add_trace(go.Scatter(
                x=dates, y=bench_vals,
                name=bench_label,
                line=dict(color=bench_colors.get(bench_label, MUTED_LINE), width=1.5, dash="dot"),
                connectgaps=False,
                customdata=[
                    f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" if v is not None else ""
                    for v in bench_vals
                ],
                hovertemplate="%{customdata}<extra>" + bench_label + "</extra>",
            ))

    # Y-axis scaling adjustments
    ys = [v for tr in fig.data if tr.y is not None for v in tr.y if v is not None]
    if ys:
        if is_log and mode in ("value", "profit"):
            pos_ys = [v for v in ys if v > 0]
            if pos_ys:
                min_val = min(pos_ys) * 0.98
                max_val = max(pos_ys) * 1.02
                fig.update_yaxes(type="log", range=[math.log10(max(min_val, 1e-4)), math.log10(max_val)])
        elif mode == "drawdown":
            min_dd = min(ys)
            fig.update_yaxes(range=[min(min_dd * 1.08, -1.0), 0.5])
        elif mode in ("twr", "mwr"):
            lo, hi = min(ys), max(ys)
            pad = max((hi - lo) * 0.05, 1.0)
            fig.update_yaxes(range=[lo - pad, hi + pad])
        elif mode == "profit":
            lo, hi = min(min(ys), 0.0), max(max(ys), 0.0)
            pad = max((hi - lo) * 0.05, 1.0)
            fig.update_yaxes(range=[lo - pad, hi + pad])
        elif mode == "value":
            fig.update_yaxes(range=[min(ys) * 0.98, max(ys) * 1.02])

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
    st.plotly_chart(fig, width="stretch", key=f"portfolio_main_{mode}", config={"displayModeBar": False})


def render_benchmarking_section(
    T: dict[str, str],
    base_ccy: str,
    snapshots: list[dict],
    bench_by_date: dict[str, dict],
    benchmarks: dict[str, str],
    bench_colors: dict[str, str],
    bench_mode: str = "twr",
    project_name: str = "Portfel",
) -> None:
    """Render the dedicated FundStat-style Benchmarking comparison section supporting multiple modes."""
    if not snapshots:
        return

    dates = [s["date"] for s in snapshots]
    SYM = {"PLN": " zł", "EUR": " €", "USD": " $"}
    mode = bench_mode.lower()
    if mode in ("wynik portfela", "stopa zwrotu"):
        mode = "twr"
    elif mode in ("zwrot inwestora",):
        mode = "mwr"
    elif mode in ("wartość portfela", "wartość"):
        mode = "value"
    elif mode in ("zysk całkowity", "zysk"):
        mode = "profit"

    bench_selected = st.session_state.get("bench_persist", list(benchmarks.keys())[:2])
    fig = go.Figure()
    ranking_items = []

    # ── 1. Calculate Portfolio Series & Format ──
    if mode == "twr":
        twr_0 = float(snapshots[0].get("twr", 0.0))
        port_series = [
            round(((1.0 + float(s.get("twr", 0.0))) / (1.0 + twr_0) - 1.0) * 100.0, 2)
            if (1.0 + twr_0) > 1e-9 else 0.0
            for s in snapshots
        ]
        port_val = port_series[-1] if port_series else 0.0
        fig.add_trace(go.Scatter(
            x=dates, y=port_series,
            name=project_name,
            line=dict(color="#1150EC", width=2.5),
            hovertemplate="%{y:+.2f}%<extra>" + project_name + "</extra>",
        ))
        ranking_items.append({
            "name": project_name,
            "ticker": "BASE",
            "val": port_val,
            "is_portfolio": True,
            "color": "#1150EC",
        })
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=True, zerolinecolor=T["chart_zeroline"],
            tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            ticksuffix="%",
            tickformat="+.1f",
        )
        col_hdr_metric = "Stopa zwrotu (TWR)"

    elif mode == "mwr":
        port_series = [
            round(((float(s.get("total_value", 0.0)) - float(s.get("invested", 0.0))) / float(s.get("invested", 1.0)) * 100.0), 2)
            if float(s.get("invested", 0.0)) > 0 else 0.0
            for s in snapshots
        ]
        port_val = port_series[-1] if port_series else 0.0
        fig.add_trace(go.Scatter(
            x=dates, y=port_series,
            name=project_name,
            line=dict(color="#1150EC", width=2.5),
            hovertemplate="%{y:+.2f}%<extra>" + project_name + "</extra>",
        ))
        ranking_items.append({
            "name": project_name,
            "ticker": "BASE",
            "val": port_val,
            "is_portfolio": True,
            "color": "#1150EC",
        })
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=True, zerolinecolor=T["chart_zeroline"],
            tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            ticksuffix="%",
            tickformat="+.1f",
        )
        col_hdr_metric = "Zwrot inwestora (MWR)"

    elif mode == "value":
        port_series = [round(float(s.get("total_value", 0.0)), 2) for s in snapshots]
        port_val = port_series[-1] if port_series else 0.0
        fig.add_trace(go.Scatter(
            x=dates, y=port_series,
            name=project_name,
            line=dict(color="#1150EC", width=2.5),
            customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in port_series],
            hovertemplate="%{customdata}<extra>" + project_name + "</extra>",
        ))
        ranking_items.append({
            "name": project_name,
            "ticker": "BASE",
            "val": port_val,
            "is_portfolio": True,
            "color": "#1150EC",
        })
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=False,
            tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
            tickprefix="" if base_ccy == "PLN" else SYM.get(base_ccy, ""),
            tickformat=",.0f",
        )
        col_hdr_metric = f"Wartość ({base_ccy})"

    else:  # mode == "profit"
        port_series = [
            round(float(s.get("pnl", float(s.get("total_value", 0.0)) - float(s.get("invested", 0.0)))), 2)
            for s in snapshots
        ]
        port_val = port_series[-1] if port_series else 0.0
        fig.add_trace(go.Scatter(
            x=dates, y=port_series,
            name=project_name,
            line=dict(color="#1150EC", width=2.5),
            customdata=[f"{v:+,.2f}".replace(",", " ") + f" {base_ccy}" for v in port_series],
            hovertemplate="%{customdata}<extra>" + project_name + "</extra>",
        ))
        ranking_items.append({
            "name": project_name,
            "ticker": "BASE",
            "val": port_val,
            "is_portfolio": True,
            "color": "#1150EC",
        })
        yaxis_cfg = dict(
            showgrid=True, gridcolor=T["chart_grid"],
            zeroline=True, zerolinecolor=T["chart_zeroline"],
            tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
            tickprefix="" if base_ccy == "PLN" else SYM.get(base_ccy, ""),
            tickformat=",.0f",
        )
        col_hdr_metric = f"Zysk całkowity ({base_ccy})"

    # ── 2. Calculate Benchmark Series ──
    price_cache: dict = {}
    for bench_label, bench_ticker in benchmarks.items():
        if bench_label not in bench_selected:
            continue

        b_color = bench_colors.get(bench_label, "#f59e0b")

        if mode == "twr":
            raw_prices = [
                get_price(bench_ticker, d, price_cache, int(d[:4]), adjusted=True)
                for d in dates
            ]
            last_known = None
            filled_prices = []
            for p in raw_prices:
                if p is not None and p > 0:
                    last_known = p
                filled_prices.append(last_known)

            first_p = next((p for p in filled_prices if p is not None and p > 0), None)
            if first_p is None or first_p <= 0:
                continue

            bench_series = [
                round(((p / first_p) - 1.0) * 100.0, 2)
                if p is not None else None
                for p in filled_prices
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=bench_series,
                name=bench_label,
                line=dict(color=b_color, width=2.0),
                connectgaps=False,
                hovertemplate="%{y:+.2f}%<extra>" + bench_label + "</extra>",
            ))
            last_valid = next((v for v in reversed(bench_series) if v is not None), 0.0)

        elif mode == "mwr":
            bench_series = [
                round(((float(bench_by_date.get(s["date"], {}).get(bench_ticker, 0.0)) - float(s.get("invested", 0.0))) / float(s.get("invested", 1.0)) * 100.0), 2)
                if float(s.get("invested", 0.0)) > 0 else 0.0
                for s in snapshots
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=bench_series,
                name=bench_label,
                line=dict(color=b_color, width=2.0),
                connectgaps=False,
                hovertemplate="%{y:+.2f}%<extra>" + bench_label + "</extra>",
            ))
            last_valid = bench_series[-1] if bench_series else 0.0

        elif mode == "value":
            bench_series = [
                round(float(bench_by_date.get(s["date"], {}).get(bench_ticker, 0.0)), 2)
                for s in snapshots
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=bench_series,
                name=bench_label,
                line=dict(color=b_color, width=2.0),
                connectgaps=False,
                customdata=[f"{v:,.2f}".replace(",", " ") + f" {base_ccy}" for v in bench_series],
                hovertemplate="%{customdata}<extra>" + bench_label + "</extra>",
            ))
            last_valid = bench_series[-1] if bench_series else 0.0

        else:  # mode == "profit"
            bench_series = [
                round(float(bench_by_date.get(s["date"], {}).get(bench_ticker, 0.0)) - float(s.get("invested", 0.0)), 2)
                for s in snapshots
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=bench_series,
                name=bench_label,
                line=dict(color=b_color, width=2.0),
                connectgaps=False,
                customdata=[f"{v:+,.2f}".replace(",", " ") + f" {base_ccy}" for v in bench_series],
                hovertemplate="%{customdata}<extra>" + bench_label + "</extra>",
            ))
            last_valid = bench_series[-1] if bench_series else 0.0

        ranking_items.append({
            "name": bench_label,
            "ticker": bench_ticker,
            "val": last_valid,
            "is_portfolio": False,
            "color": b_color,
        })

    fig.update_layout(
        template=T["plotly_template"],
        paper_bgcolor=T["chart_bg"],
        plot_bgcolor=T["chart_bg"],
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
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
        ),
        yaxis=yaxis_cfg,
    )

    st.plotly_chart(fig, width="stretch", key=f"benchmarking_chart_{mode}", config={"displayModeBar": False})

    # ── 3. Ranking Table ──
    ranking_items.sort(key=lambda x: x["val"], reverse=True)

    st.markdown(
        f"""
        <div style="border-top: 1px solid {T['border']}; margin-top: 0.8rem; padding-top: 0.6rem;">
        </div>
        """,
        unsafe_allow_html=True,
    )

    h_cols = st.columns([0.6, 3.8, 2.4, 2.4, 2.0])
    for col, label in zip(h_cols, ["#", "Instrument", col_hdr_metric, f"vs {project_name}", "Status"]):
        with col:
            st.markdown(f"<span class='h-col-hdr'>{label}</span>", unsafe_allow_html=True)
    st.markdown("<div class='h-hdr'></div>", unsafe_allow_html=True)

    for rank, item in enumerate(ranking_items, 1):
        c_rank, c_name, c_ret, c_diff, c_status = st.columns([0.6, 3.8, 2.4, 2.4, 2.0])
        val = item["val"]

        if mode in ("twr", "mwr"):
            val_col = POSITIVE if val >= 0 else NEGATIVE
            val_str = f"{val:+.2f}%"
        elif mode == "profit":
            val_col = POSITIVE if val >= 0 else NEGATIVE
            val_str = f"{val:+,.2f}".replace(",", " ") + f" {base_ccy}"
        else:  # value
            val_col = T["text"]
            val_str = f"{val:,.2f}".replace(",", " ") + f" {base_ccy}"

        with c_rank:
            st.markdown(f"<div class='h-cell' style='font-weight:700;'>{rank}</div>", unsafe_allow_html=True)

        with c_name:
            st.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:0.5rem;padding:4px 0;">
                  <div style="width:10px;height:10px;border-radius:50%;background:{item['color']};flex-shrink:0;"></div>
                  <span style="font-weight:600;color:{T['text']};">{item['name']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c_ret:
            st.markdown(f"<div class='h-cell' style='color:{val_col};font-weight:700;'>{val_str}</div>", unsafe_allow_html=True)

        with c_diff:
            if item["is_portfolio"]:
                st.markdown(f"<div class='h-cell' style='color:{T['text_muted']};font-weight:600;'>Baza</div>", unsafe_allow_html=True)
            else:
                diff_val = val - port_val
                diff_col = POSITIVE if diff_val >= 0 else NEGATIVE
                if mode in ("twr", "mwr"):
                    diff_str = f"{diff_val:+.1f} p.p."
                elif mode in ("value", "profit"):
                    diff_str = f"{diff_val:+,.0f}".replace(",", " ") + f" {base_ccy}"
                st.markdown(f"<div class='h-cell' style='color:{diff_col};font-weight:700;'>{diff_str}</div>", unsafe_allow_html=True)

        with c_status:
            if item["is_portfolio"]:
                st.markdown(
                    f"<div class='h-cell'><span class='h-days-badge' style='background:{ACCENT}22;color:{ACCENT};font-weight:700;'>Punkt odniesienia</span></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"<div class='h-cell' style='color:{T['text_muted']};'>Benchmark</div>", unsafe_allow_html=True)

        st.markdown("<div class='holdings-row'></div>", unsafe_allow_html=True)
