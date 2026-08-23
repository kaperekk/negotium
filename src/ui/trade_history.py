from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from ticker_data import get_fx_rate, get_price
from transactions import get_ticker_history
from ui.styles import (
    build_trade_dialog_styles,
    render_trade_empty_state,
    render_trade_summary_cards,
    render_trade_table_html,
)


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
                line=dict(color="#6C63FF", width=2),
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
            ))

            buys = [t for t in enriched if t["side"] == "Buy" and t["price"] is not None]
            sells = [t for t in enriched if t["side"] == "Sell" and t["price"] is not None]

            if buys:
                fig.add_trace(go.Scatter(
                    x=[date.fromisoformat(t["date"]) for t in buys],
                    y=[t["price"] for t in buys],
                    mode="markers", name="Buy",
                    marker=dict(color="#22c55e", size=12, symbol="triangle-up"),
                    hovertemplate="%{x|%Y-%m-%d}<br>Buy %{y:.2f}<extra></extra>",
                ))
            if sells:
                fig.add_trace(go.Scatter(
                    x=[date.fromisoformat(t["date"]) for t in sells],
                    y=[t["price"] for t in sells],
                    mode="markers", name="Sell",
                    marker=dict(color="#ef4444", size=12, symbol="triangle-down"),
                    hovertemplate="%{x|%Y-%m-%d}<br>Sell %{y:.2f}<extra></extra>",
                ))

            fig.update_layout(
                xaxis_title="Date",
                yaxis_title="Price",
                template=T["plotly_template"],
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
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
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

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

        components.html(
            render_trade_table_html(T, trade_df),
            height=50 + 48 * len(trade_df),
            scrolling=True,
        )

    _show()
