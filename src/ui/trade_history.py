from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ticker_data import get_dividends, get_fx_rate, get_price
from ledger_core import get_ticker_history, get_ticker_legs
from ui.colors import ACCENT, DIVIDEND, NEGATIVE, POSITIVE
from ui.styles import (
    build_trade_dialog_styles,
    render_trade_empty_state,
    render_trade_summary_cards,
    render_trade_table_html,
)

@st.dialog("Confirm delete")
def _confirm_delete(ticker: str, history: list[dict], idx: int, storage) -> None:
    """Show confirmation dialog before deleting a transaction."""
    if idx < 0 or idx >= len(history):
        st.error("Invalid row number.")
        return
    trade = history[idx]
    st.warning(
        f"Delete this transaction?\n\n"
        f"**Date:** {trade['date']}\n"
        f"**Side:** {trade['side']}\n"
        f"**Shares:** {trade['amount']:.4f}\n\n"
        f"This action cannot be undone."
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancel", key="del_cancel", width="stretch"):
            st.rerun()
    with col2:
        if st.button("Delete", key="del_confirm", width="stretch", type="primary"):
            delete_transaction(trade["date"], 0)
            st.success("Transaction deleted.")
            st.session_state["force_refresh"] = True
            for k in list(st.session_state.keys()):
                if k.startswith("snapshots_") or k.startswith("benchmarks_"):
                    st.session_state.pop(k)
            storage.invalidate_portfolio_from(trade["date"])
            st.rerun()

def render_trade_history_dialog(T: dict[str, str], ticker: str, name: str, ccy: str,
                               base_ccy: str, today, storage) -> None:
    @st.dialog("Trade history", width="large")
    def _show():
        st.subheader(f"{name} ({ticker})")
        st.markdown(build_trade_dialog_styles(T), unsafe_allow_html=True)

        history = get_ticker_history(ticker)
        if not history:
            st.markdown(render_trade_empty_state(T), unsafe_allow_html=True)
            return

        current_price = get_price(ticker, today.isoformat(), {}, today.year)
        price_cache: dict = {}
        fx_cache: dict = {}
        enriched = []
        for trade in history:
            yr = int(trade["date"][:4])
            price = get_price(ticker, trade["date"], price_cache, yr)
            if ccy != base_ccy:
                fx = get_fx_rate(ccy, base_ccy, trade["date"], fx_cache, yr)
            else:
                fx = 1.0
            val_native = trade["amount"] * price if price is not None else None
            val_base = val_native * fx if val_native is not None else None
            if trade["side"] == "Buy" and price is not None and current_price is not None:
                ret = (current_price / price) - 1
            else:
                ret = None
            enriched.append({
                **trade,
                "price": price,
                "fx": fx,
                "value_native": val_native,
                "value_base": val_base,
                "ret": ret,
            })

        total_bought = sum(t["amount"] for t in history if t["side"] == "Buy")
        total_sold = sum(abs(t["amount"]) for t in history if t["side"] == "Sell")
        net = total_bought - total_sold

        st.markdown(render_trade_summary_cards(T, total_bought, total_sold, net), unsafe_allow_html=True)

        # ── Legs view: full transaction entries for each trade date ──────────
        st.markdown("##### Trade legs (full transaction entries)")
        legs_rows: list[dict] = []
        for leg_grp in get_ticker_legs(ticker):
            # Build a readable line like  "+10 AAPL  /  -1500 USD"
            legs_txt = "  /  ".join(
                f"{'+' if l['amount'] > 0 else ''}{l['amount']:+.4f} {l['ticker']}"
                + ("  🏷️" if l.get("account_operation") else "")
                for l in leg_grp["legs"]
            )
            legs_rows.append({"Date": leg_grp["date"], "Entries": legs_txt})
        if legs_rows:
            legs_df = pd.DataFrame(legs_rows)
            st.iframe(
                render_trade_table_html(T, legs_df),
                height=50 + 48 * len(legs_df),
            )

        # Dividend history (per-share, native currency) + yield at ex-date
        dividends = get_dividends(ticker)
        div_cache: dict = {}
        div_rows: list[dict] = []
        for d, amount in sorted(dividends.items()):
            yr = int(d[:4])
            price = get_price(ticker, d, div_cache, yr)
            pct = (amount / price * 100.0) if price else None
            div_rows.append({"date": d, "amount": amount, "price": price, "pct": pct})

        first_trade_date = date.fromisoformat(history[0]["date"])
        chart_start = first_trade_date.replace(year=first_trade_date.year - 1)

        all_prices: dict[str, float] = {}
        for yr in range(chart_start.year, today.year + 1):
            year_data = storage.load_price_year(ticker, yr)
            all_prices.update(year_data)

        if all_prices:
            sorted_dates = sorted(all_prices.keys())
            price_dates = [date.fromisoformat(d) for d in sorted_dates]
            price_values = [all_prices[d] for d in sorted_dates]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=price_dates, y=price_values,
                mode="lines", name="Price",
                line=dict(color=ACCENT, width=2),
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
            ))

            buys = [t for t in enriched if t["side"] == "Buy" and t["price"] is not None]
            sells = [t for t in enriched if t["side"] == "Sell" and t["price"] is not None]

            if buys:
                fig.add_trace(go.Scatter(
                    x=[date.fromisoformat(t["date"]) for t in buys],
                    y=[t["price"] for t in buys],
                    mode="markers", name="Buy",
                    marker=dict(color=POSITIVE, size=12, symbol="triangle-up"),
                    hovertemplate="%{x|%Y-%m-%d}<br>Buy %{y:.2f}<extra></extra>",
                ))
            if sells:
                fig.add_trace(go.Scatter(
                    x=[date.fromisoformat(t["date"]) for t in sells],
                    y=[t["price"] for t in sells],
                    mode="markers", name="Sell",
                    marker=dict(color=NEGATIVE, size=12, symbol="triangle-down"),
                    hovertemplate="%{x|%Y-%m-%d}<br>Sell %{y:.2f}<extra></extra>",
                ))

            div_markers = [r for r in div_rows if r["price"] is not None]
            if div_markers:
                fig.add_trace(go.Scatter(
                    x=[date.fromisoformat(r["date"]) for r in div_markers],
                    y=[r["price"] for r in div_markers],
                    mode="markers", name="Dividend",
                    marker=dict(color=DIVIDEND, size=11, symbol="star"),
                    hovertemplate=(
                        "%{x|%Y-%m-%d}<br>Dividend %{customdata:.4f} "
                        f"{ccy} (%{{y:.2f}})<extra></extra>"
                    ),
                    customdata=[r["amount"] for r in div_markers],
                ))

            fig.update_layout(
                xaxis_title="Date",
                yaxis_title="Price",
                template=T["plotly_template"],
                paper_bgcolor=T["chart_bg"],
                plot_bgcolor=T["chart_bg"],
                margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(
                    rangeslider=dict(visible=True, thickness=0.05),
                    rangeselector=dict(
                        buttons=[
                            dict(count=1, label="1M", step="month", stepmode="backward"),
                            dict(count=3, label="3M", step="month", stepmode="backward"),
                            dict(count=6, label="6M", step="month", stepmode="backward"),
                            dict(count=1, label="1Y", step="year", stepmode="backward"),
                            dict(step="all", label="All"),
                        ],
                        bgcolor=T["range_bg"],
                        activecolor=T["range_active"],
                        font=dict(color=T["text"]),
                    ),
                ),
            )
            st.plotly_chart(fig, width='stretch', key=f"trade_history_{ticker}", config={"displayModeBar": False})

        trade_df = pd.DataFrame([{
            "Date": t["date"],
            "Side": t["side"],
            "Shares": f'{t["amount"]:.4f}' if t["amount"] is not None else None,
            "Price": f'{t["price"]:.2f}' if t["price"] is not None else None,
            "Value": f'{t["value_native"]:.2f}' if t["value_native"] is not None else None,
            "FX": f'{t["fx"]:.4f}' if ccy != base_ccy and t["fx"] is not None else None,
            f"Value ({base_ccy})": f'{t["value_base"]:.2f}' if t["value_base"] is not None else None,
            "Return": f'{t["ret"] * 100:.1f}%' if t["ret"] is not None else None,
        } for t in enriched])

        st.iframe(
            render_trade_table_html(T, trade_df),
            height=50 + 48 * len(trade_df),
        )

        # Delete transaction section
        st.markdown("### Delete transaction")
        del_col1, del_col2 = st.columns([2, 1])
        with del_col1:
            del_idx = st.number_input(
                "Row # to delete",
                min_value=1,
                max_value=len(trade_df),
                value=1,
                step=1,
                key="del_row_idx",
                help="Enter the row number from the table above",
            )
        with del_col2:
            if st.button("🗑️ Delete", key="del_tx_btn", width="stretch"):
                _confirm_delete(ticker, history, int(del_idx) - 1, storage)

        if div_rows:
            div_df = pd.DataFrame([{
                "Date": r["date"],
                "Dividend %": f'{r["pct"]:.2f}%' if r["pct"] is not None else None,
                f"Dividend ({ccy})": f'{r["amount"]:.4f}',
            } for r in div_rows])
            st.markdown("### Dividends")
            st.iframe(
                render_trade_table_html(T, div_df),
                height=50 + 48 * len(div_df),
            )

    _show()
