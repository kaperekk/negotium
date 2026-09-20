from __future__ import annotations

import streamlit as st

from ui.styles import build_metric_card_styles, build_toggle_button_styles, render_metric_cards


def render_metric_section(T: dict[str, str], base_ccy: str, cur_value: float, contrib: float,
                         best_ticker: str, twr_str: str, irr_str: str, fmt) -> None:
    st.markdown(build_metric_card_styles(T), unsafe_allow_html=True)
    st.markdown(
        render_metric_cards(
            T,
            total_value=fmt(cur_value),
            invested=fmt(contrib),
            largest_position=best_ticker,
            twr=twr_str,
            irr=irr_str,
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
