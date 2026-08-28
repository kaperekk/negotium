from __future__ import annotations

import streamlit as st

from ui.colors import ACCENT, NEGATIVE, RETURN_UP
from ui.styles import build_holdings_styles


def render_holdings_table(T: dict[str, str], latest_assets, base_ccy: str, today, storage,
                         get_fx_rate, get_ticker_name, show_trade_dialog) -> None:
    if not latest_assets:
        return

    total_val = max(sum(a["value_base"] for a in latest_assets), 1.0)
    bal = storage.load_balance()

    rows = []
    avg_fx_cache: dict = {}
    ticker_names = {a["ticker"]: get_ticker_name(a["ticker"]) for a in latest_assets}
    for a in sorted(latest_assets, key=lambda x: x["value_base"], reverse=True):
        ticker = a["ticker"]
        shares = a["amount"]
        value = a["value_base"]
        avg_raw = bal.get(ticker, {}).get("avg_price", 0.0)
        ticker_ccy = a.get("currency", "PLN")
        if ticker_ccy != base_ccy:
            avg_ccy_fx = get_fx_rate(ticker_ccy, base_ccy, today.isoformat(), avg_fx_cache, today.year)
        else:
            avg_ccy_fx = 1.0
        avg = avg_raw * avg_ccy_fx
        cost_basis = shares * avg
        ret_pct = ((value / cost_basis) - 1) * 100 if cost_basis else 0.0
        rows.append({
            "ticker": ticker,
            "name": ticker_names.get(ticker, ticker),
            "ccy": a.get("currency", "—"),
            "weight": value / total_val * 100,
            "shares": shares,
            "value": value,
            "ret_pct": ret_pct,
        })

    def _fmt_val(v: float) -> str:
        s = f"{v:,.1f}".replace(",", " ")
        return f"{SYM.get(base_ccy, '')}{s}" if base_ccy != "PLN" else f"{s} PLN"

    def _fmt_ret(p: float) -> str:
        return f"{p:+.1f}%"

    def _ret_color(p: float) -> str:
        return RETURN_UP if p >= 0 else NEGATIVE

    SYM = {"PLN": " PLN", "EUR": "€", "USD": "$"}
    max_weight = max((r["weight"] for r in rows), default=1) or 1

    st.markdown(build_holdings_styles(T), unsafe_allow_html=True)

    headers = st.columns([5, 1, 1, 1, 2, 1])
    for col, label in zip(headers, ["Ticker", "CCY", "Weight", "Shares", "Value", "Return %"]):
        with col:
            st.markdown(f"<span class='h-col-hdr'>{label}</span>", unsafe_allow_html=True)
    st.markdown("<div class='h-hdr'></div>", unsafe_allow_html=True)

    for r in rows:
        bar_pct = r["weight"]
        ret_col = _ret_color(r["ret_pct"])
        left, ccy, weight, shares, value, ret = st.columns([5, 1, 1, 1, 2, 1])

        with left:
            btn_label = f"{r['ticker']}  |  {r['name']}" if r["name"] != r["ticker"] else r["ticker"]
            if st.button(
                btn_label,
                key=f"hbtn_{r['ticker']}",
                help=f"Trade history for {r['ticker']}",
                width='stretch',
            ):
                show_trade_dialog(r["ticker"], r["name"], r["ccy"])
            st.markdown(
                f"<div style=\"margin-top:-0.6rem;margin-bottom:0.2rem;border-radius:4px;overflow:hidden;height:4px;background:{T['holdings_bar_bg']};\">"
                f"<div style=\"width:{bar_pct / max_weight * 100:.1f}%;height:100%;background:{ACCENT};border-radius:4px;\"></div></div>",
                unsafe_allow_html=True,
            )
        with ccy:
            st.markdown(f"<div class='h-cell'>{r['ccy']}</div>", unsafe_allow_html=True)
        with weight:
            st.markdown(f"<div class='h-cell'>{r['weight']:.1f}%</div>", unsafe_allow_html=True)
        with shares:
            st.markdown(f"<div class='h-cell'>{r['shares']:.4f}</div>", unsafe_allow_html=True)
        with value:
            st.markdown(f"<div class='h-cell'>{_fmt_val(r['value'])}</div>", unsafe_allow_html=True)
        with ret:
            st.markdown(f"<div class='h-cell' style='color:{ret_col};font-weight:600'>{_fmt_ret(r['ret_pct'])}</div>", unsafe_allow_html=True)
        st.markdown("<div class='holdings-row'></div>", unsafe_allow_html=True)
