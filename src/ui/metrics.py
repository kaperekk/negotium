from __future__ import annotations

import streamlit as st

from ui.styles import build_metric_card_styles, build_toggle_button_styles, render_metric_cards


from ui.styles import (
    build_metric_card_styles,
    build_toggle_button_styles,
    render_metric_cards,
    render_fundstat_metric_cards,
)


def render_metric_section(
    T: dict[str, str],
    base_ccy: str,
    cur_value: float,
    contrib: float,
    best_ticker: str = "",
    twr_str: str = "—",
    irr_str: str = "—",
    fmt=None,
    *,
    pnl: float | None = None,
    pnl_pct: float | None = None,
    twr_cum_str: str | None = None,
    twr_ann_str: str | None = None,
    mwr_cum_str: str | None = None,
    mwr_ann_str: str | None = None,
) -> None:
    st.markdown(build_metric_card_styles(T), unsafe_allow_html=True)

    if pnl is None:
        pnl = cur_value - contrib
    if pnl_pct is None:
        pnl_pct = (pnl / contrib * 100) if contrib else 0.0

    sign = "+" if pnl >= 0 else ""
    gain_formatted = f"{sign}{fmt(pnl)}" if fmt else f"{sign}{pnl:,.0f} {base_ccy}"
    gain_pct_formatted = f"{sign}{pnl_pct:.2f}%"

    inv_cum = mwr_cum_str or (f"{sign}{pnl_pct:.2f}%" if pnl_pct is not None else "—")
    inv_ann = mwr_ann_str or (f"{irr_str}" if irr_str != "—" else "—")
    port_cum = twr_cum_str or twr_str
    port_ann = twr_ann_str or twr_str

    st.markdown(
        render_fundstat_metric_cards(
            T,
            total_value=fmt(cur_value) if fmt else f"{cur_value:,.0f} {base_ccy}",
            total_gain_str=gain_formatted,
            total_gain_pct_str=gain_pct_formatted,
            is_gain_positive=(pnl >= 0),
            investor_return_cum=inv_cum,
            investor_return_ann=inv_ann,
            portfolio_return_cum=port_cum,
            portfolio_return_ann=port_ann,
            base_ccy=base_ccy,
        ),
        unsafe_allow_html=True,
    )


def render_pnl_toggle_section(T: dict[str, str], cur_value: float, pnl: float, pnl_pct: float, fmt) -> None:
    if "chart_mode" not in st.session_state:
        st.session_state.chart_mode = "amount"

    sign = "+" if pnl >= 0 else ""
    mode = st.session_state.chart_mode

    st.markdown(build_toggle_button_styles(T), unsafe_allow_html=True)
    left, mid, right = st.columns(3)

    with left:
        if st.button(
            f"Value · {fmt(cur_value)}",
            key="pnl_amount_btn",
            type="primary" if mode == "amount" else "secondary",
            width='stretch',
        ):
            st.session_state.chart_mode = "amount"
            st.rerun()

    with mid:
        if st.button(
            f"P&L · {sign}{fmt(pnl)}",
            key="pnl_profit_btn",
            type="primary" if mode == "profit" else "secondary",
            width='stretch',
        ):
            st.session_state.chart_mode = "profit"
            st.rerun()

    with right:
        if st.button(
            f"Return · {sign}{pnl_pct:.1f}%",
            key="pnl_pct_btn",
            type="primary" if mode == "percent" else "secondary",
            width='stretch',
        ):
            st.session_state.chart_mode = "percent"
            st.rerun()
