from __future__ import annotations

import streamlit as st

from ui.styles import build_metric_card_styles, build_toggle_button_styles, render_metric_cards


def render_metric_section(T: dict[str, str], base_ccy: str, cur_value: float, contrib: float,
                         best_ticker: str, cagr_str: str, irr_str: str, fmt) -> None:
    st.markdown(build_metric_card_styles(T), unsafe_allow_html=True)
    st.markdown(
        render_metric_cards(
            T,
            total_value=fmt(cur_value),
            invested=fmt(contrib),
            largest_position=best_ticker,
            cagr=cagr_str,
            irr=irr_str,
            base_ccy=base_ccy,
        ),
        unsafe_allow_html=True,
    )


def render_pnl_toggle_section(T: dict[str, str], pnl: float, pnl_pct: float, fmt) -> None:
    if "chart_mode" not in st.session_state:
        st.session_state.chart_mode = "amount"

    sign = "+" if pnl >= 0 else ""
    is_amount = st.session_state.chart_mode == "amount"
    is_percent = not is_amount

    st.markdown(build_toggle_button_styles(T), unsafe_allow_html=True)
    left, right = st.columns(2)

    with left:
        if st.button(
            f"Total P&L  ·  {sign}{fmt(pnl)}",
            key="pnl_amount_btn",
            type="primary" if is_amount else "secondary",
            width='stretch',
        ):
            st.session_state.chart_mode = "amount"
            st.rerun()

    with right:
        if st.button(
            f"Total Return  ·  {sign}{pnl_pct:.1f}%",
            key="pnl_pct_btn",
            type="primary" if is_percent else "secondary",
            width='stretch',
        ):
            st.session_state.chart_mode = "percent"
            st.rerun()
