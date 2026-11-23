from __future__ import annotations

import streamlit as st

from ui.colors import ACCENT, NEGATIVE, RETURN_UP
from ui.styles import build_holdings_styles
from ledger_core import get_holding_days


def render_holdings_table(T: dict[str, str], latest_assets, base_ccy: str, today, storage,
                         get_fx_rate, get_ticker_name, show_trade_dialog) -> None:
    if not latest_assets:
        return

    total_val = max(sum(a["value_base"] for a in latest_assets), 1.0)
    bal = storage.load_balance()

    stock_rows = []
    cash_rows = []
    avg_fx_cache: dict = {}
    ticker_names = {a["ticker"]: get_ticker_name(a["ticker"]) for a in latest_assets}

    SYM = {"PLN": " zł", "EUR": " €", "USD": " $"}

    for a in sorted(latest_assets, key=lambda x: x["value_base"], reverse=True):
        ticker = a["ticker"]
        shares = a["amount"]
        value = a["value_base"]
        ticker_ccy = a.get("currency", "PLN")
        weight = (value / total_val) * 100

        is_cash = ticker in storage.SUPPORTED_CURRENCIES

        if is_cash:
            cash_rows.append({
                "ticker": ticker,
                "name": f"Gotówka ({ticker})",
                "is_cash": True,
                "ccy": ticker,
                "weight": weight,
                "shares": shares,
                "value": value,
                "days": None,
                "pnl": None,
                "ret_pct": None,
                "avg_price": None,
            })
        else:
            avg_raw = bal.get(ticker, {}).get("avg_price", 0.0)
            if ticker_ccy != base_ccy:
                avg_ccy_fx = get_fx_rate(ticker_ccy, base_ccy, today.isoformat(), avg_fx_cache, today.year)
            else:
                avg_ccy_fx = 1.0
            avg_base = avg_raw * avg_ccy_fx
            cost_basis = shares * avg_base
            pnl = value - cost_basis
            ret_pct = ((value / cost_basis) - 1.0) * 100.0 if cost_basis else 0.0
            days = get_holding_days(ticker, today)

            stock_rows.append({
                "ticker": ticker,
                "name": ticker_names.get(ticker, ticker),
                "is_cash": False,
                "ccy": ticker_ccy,
                "weight": weight,
                "shares": shares,
                "value": value,
                "days": days,
                "pnl": pnl,
                "ret_pct": ret_pct,
                "avg_price": avg_raw,
            })

    rows = stock_rows + cash_rows
    max_weight = max((r["weight"] for r in rows), default=1.0) or 1.0

    def _fmt_money(v: float | None, ccy: str) -> str:
        if v is None:
            return "—"
        sign = "+" if v > 0 else ""
        s = f"{v:,.2f}".replace(",", " ")
        if ccy == "PLN":
            return f"{s} zł"
        elif ccy == "USD":
            return f"{s} USD"
        elif ccy == "EUR":
            return f"{s} €"
        return f"{s} {ccy}"

    def _fmt_pnl(v: float | None) -> str:
        if v is None:
            return "—"
        sign = "+" if v >= 0 else ""
        s = f"{abs(v):,.2f}".replace(",", " ")
        return f"{sign}{s} zł" if base_ccy == "PLN" else f"{sign}{s} {base_ccy}"

    def _fmt_ret(p: float | None) -> str:
        if p is None:
            return "—"
        return f"{p:+.2f}%"

    st.markdown(build_holdings_styles(T), unsafe_allow_html=True)

    # Header with date and count
    st.markdown(
        f"""
        <div class="section-header-box">
          <div class="section-title">
            <span>Aktywa</span>
          </div>
          <div class="section-date-badge">Dane z dnia: {today.strftime('%d %b %Y')} · {len(stock_rows)} pozycji</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Columns: Instrument, Udział, Dni, P&L, P&L %, Wartość, Cena wejścia, Historia
    headers = st.columns([3.0, 1.1, 0.7, 1.4, 1.1, 1.4, 1.3, 0.7])
    col_labels = ["Instrument", "Udział", "Dni", "P&L", "P&L %", "Wartość", "Cena wejścia", "Historia"]
    for col, label in zip(headers, col_labels):
        with col:
            st.markdown(f"<span class='h-col-hdr'>{label}</span>", unsafe_allow_html=True)
    st.markdown("<div class='h-hdr'></div>", unsafe_allow_html=True)

    for r in rows:
        c_inst, c_weight, c_days, c_pnl, c_ret, c_val, c_entry, c_hist = st.columns([3.0, 1.1, 0.7, 1.4, 1.1, 1.4, 1.3, 0.7])

        ticker = r["ticker"]
        clean_sym = ticker.split(".")[0].upper()
        initials = clean_sym[:2] if len(clean_sym) >= 2 else clean_sym

        if r["is_cash"]:
            logo_url = f"https://logo.twelvedata.com/forex/{ticker.lower()}.png"
        else:
            logo_url = f"https://cdn.brandfetch.io/ticker/{clean_sym}/fallback/lettermark/type/icon?c=1idHuFhtG9P4b3mSOMW"

        with c_inst:
            st.markdown(
                f"""
                <div class="h-inst-box">
                  <img class="h-logo" src="{logo_url}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
                  <div class="h-logo-fallback" style="display:none;">{initials}</div>
                  <div class="h-inst-text">
                    <span class="h-inst-sym">{ticker}</span>
                    <span class="h-inst-name">{r['name']}</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c_weight:
            bar_w = (r["weight"] / max_weight) * 100
            st.markdown(
                f"""
                <div class="h-cell" style="font-weight:600;">{r['weight']:.2f}%</div>
                <div style="margin-top:-0.4rem;margin-bottom:0.2rem;border-radius:4px;overflow:hidden;height:3px;background:{T['holdings_bar_bg']};">
                  <div style="width:{bar_w:.1f}%;height:100%;background:{ACCENT};border-radius:4px;"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c_days:
            days_str = str(r["days"]) if r["days"] is not None else "—"
            st.markdown(f"<div class='h-cell'><span class='h-days-badge'>{days_str}</span></div>", unsafe_allow_html=True)

        with c_pnl:
            pnl_val = r["pnl"]
            if pnl_val is not None:
                pnl_color = RETURN_UP if pnl_val >= 0 else NEGATIVE
                st.markdown(f"<div class='h-cell' style='color:{pnl_color};font-weight:600;'>{_fmt_pnl(pnl_val)}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='h-cell'>—</div>", unsafe_allow_html=True)

        with c_ret:
            ret_val = r["ret_pct"]
            if ret_val is not None:
                ret_color = RETURN_UP if ret_val >= 0 else NEGATIVE
                st.markdown(f"<div class='h-cell' style='color:{ret_color};font-weight:600;'>{_fmt_ret(ret_val)}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='h-cell'>—</div>", unsafe_allow_html=True)

        with c_val:
            st.markdown(f"<div class='h-cell' style='font-weight:600;'>{_fmt_money(r['value'], base_ccy)}</div>", unsafe_allow_html=True)

        with c_entry:
            avg_p = r["avg_price"]
            if avg_p is not None and avg_p > 0:
                st.markdown(f"<div class='h-cell'>{_fmt_money(avg_p, r['ccy'])}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='h-cell'>—</div>", unsafe_allow_html=True)

        with c_hist:
            if not r["is_cash"]:
                if st.button("📜", key=f"hist_{ticker}", help=f"Historia transakcji: {ticker}", width='stretch'):
                    show_trade_dialog(r["ticker"], r["name"], r["ccy"])
            else:
                st.markdown("<div class='h-cell'>—</div>", unsafe_allow_html=True)

        st.markdown("<div class='holdings-row'></div>", unsafe_allow_html=True)
