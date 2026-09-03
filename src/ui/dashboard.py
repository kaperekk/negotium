from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config as cfg_module
import storage
from bossa_import import import_bossa
from currencies import CURRENCY_SYMBOLS
from manual_import import import_manual
from portfolio_core import FX_TICKERS, build_portfolio, snapshots_to_series
from ticker_data import ensure_batch, get_fx_rate, get_price, get_ticker_name, get_ticker_meta
from ledger_core import (
    add_transaction,
    compute_cagr,
    compute_irr,
    delete_transaction,
    get_all_tickers,
    get_all_transactions,
    get_ticker_history,
    rebuild_balance,
    set_account_operation,
    update_transaction,
)
from xtb_import import import_xtb
from ui.holdings import render_holdings_table
from ui.allocation import render_allocation_breakdown
from ui.drawdown import render_drawdown_analysis
from ui.metrics import render_metric_section, render_pnl_toggle_section
from ui.colors import BENCHMARKS, BENCH_COLORS
from ui.portfolio_chart import render_portfolio_chart
from ui.styles import (
    build_app_styles,
    build_late_theme_override,
    build_streamlit_fix_script,
    render_empty_state,
)
from ui.trade_history import render_trade_history_dialog
from ui.watchlist import render_watchlist


@st.cache_data(ttl=3600)
def _ensure_batch_cached(
    tickers_tuple: tuple[str, ...],
    start_date_iso: str,
    force_refresh: bool,
) -> tuple[list[str], int]:
    """Cached price download so reruns don't re-fetch already-cached data.

    Returns (failed_tickers, call_count). The call_count increments only
    on actual downloads — cached returns keep the original count so the
    caller can tell whether a download happened this session.

    Uses st.cache_data (not cache_resource) because the return value is
    immutable data, not a shared resource like a database connection.
    """
    failed = ensure_batch(
        list(tickers_tuple),
        date.fromisoformat(start_date_iso),
        force_refresh_current_year=force_refresh,
    )
    return failed, 1


def render_dashboard(cfg, storage, T, today, data_start_date, base_ccy: str | None = None):
    precision = "D"
    if base_ccy is None:
        ccy_options = list(CURRENCY_SYMBOLS)
        complete_default = ccy_options.index(cfg.get("default_currency", "PLN"))
        base_ccy = ccy_options[st.session_state.get("base_ccy_idx", complete_default)]

    # ── Main ──────────────────────────────────────────────────────────────────────

    all_tx = get_all_transactions()
    if not all_tx:
        st.markdown(
            render_empty_state(
                "No transactions yet",
                "Add your first one using the sidebar form.",
                T,
                details='Example: Ticker 1 = <code style="color:{accent};">AAPL</code>, Amount 1 = <code style="color:{accent};">10</code> / Ticker 2 = <code style="color:{accent};">USD</code>, Amount 2 = <code style="color:{accent};">-1700</code>'.format(accent=T["accent"]),
            ),
            unsafe_allow_html=True,
        )
        st.stop()

    # ── Market data download ──────────────────────────────────────────────────────

    tickers_needed = get_all_tickers(include_fx=True)
    force_refresh  = st.session_state.pop("force_refresh", False)

    # Invalidate in-memory caches so fresh data is picked up immediately
    if force_refresh:
        from ticker_data import invalidate_recent_price_cache, invalidate_ath_cache
        invalidate_recent_price_cache()
        invalidate_ath_cache()
        _ensure_batch_cached.clear()

    # Check which tickers actually need downloading
    missing = [
        t for t in tickers_needed
        if t not in storage.SUPPORTED_CURRENCIES
        and (force_refresh or not storage.has_price_year(t, today.year))
    ]

    download_errors: list[str] = []

    if missing:
        dl_bar = st.progress(0, text=f"Downloading {len(missing)} tickers…")

        try:
            download_errors, _ = _ensure_batch_cached(
                tuple(missing),
                data_start_date.isoformat(),
                True,
            )
        except Exception as e:
            download_errors = list(missing)
            st.caption(f"⚠ Batch download failed: {e}")

        dl_bar.empty()

        if download_errors:
            st.warning(
                f"⚠️ Could not download price data for: **{', '.join(download_errors)}**\n\n"
                "These positions will be missing from the chart. "
                "Check your internet connection and try **Refresh data**."
            )

    # ── Rebuild balance after price refresh (fixes stale avg_price) ──────────────

    if force_refresh:
        rebuild_balance()

    # Warn if we have stock tickers but zero price files at all
    stock_tickers = [t for t in tickers_needed
                     if t not in storage.SUPPORTED_CURRENCIES and t not in FX_TICKERS]
    tickers_with_data = [t for t in stock_tickers if storage.has_price_year(t, today.year)
                         or any(storage.has_price_year(t, y) for y in range(data_start_date.year, today.year + 1))]
    tickers_without_data = [t for t in stock_tickers if t not in tickers_with_data]

    if tickers_without_data:
        st.error(
            f"❌ No price data available for: **{', '.join(tickers_without_data)}**\n\n"
            "These tickers will not appear in the chart. "
            "Make sure you're connected to the internet and the ticker symbols are correct "
            "(e.g. `QDVE.DE` for Xetra, `CDR.WA` for Warsaw, `AAPL` for NASDAQ)."
        )

    # ── Build portfolio ───────────────────────────────────────────────────────────

    cache_key = f"snapshots_{base_ccy}_{precision}"

    if cache_key not in st.session_state:
        bar = st.progress(0, text="Building portfolio…")

        def _on_progress(day_str: str, pct: float):
            bar.progress(min(pct, 1.0), text=f"Computing {day_str}…")

        t_start = time.perf_counter()
        all_snapshots = build_portfolio(
            start_date=data_start_date,
            end_date=today,
            base_currency=base_ccy,
            precision=precision,
            progress_cb=_on_progress,
            use_cache=True,
        )
        elapsed = time.perf_counter() - t_start
        bar.empty()

        log_path = storage._project_dir() / "build.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{today.isoformat()} {time.strftime('%H:%M:%S')} | "
                    f"{base_ccy} {precision} | {elapsed:.3f}s | "
                    f"{len(all_snapshots)} snapshots\n")

        st.session_state[cache_key] = all_snapshots

    all_snapshots: list[dict] = st.session_state[cache_key]

    # ── Download data for selected benchmarks ─────────────────────────────────────
    bench_persist = st.session_state.get("bench_persist", [])
    if bench_persist:
        bench_date_start = date.fromisoformat(all_snapshots[0]["date"])
        bench_date_end = date.fromisoformat(all_snapshots[-1]["date"])
        bench_tickers_needed = [BENCHMARKS[k] for k in bench_persist if k in BENCHMARKS]
        bench_missing = [
            t for t in bench_tickers_needed
            if t not in storage.SUPPORTED_CURRENCIES
            and (force_refresh or not storage.has_price_year(t, today.year))
        ]
        if bench_missing:
            bench_dl = st.progress(0, text="Downloading benchmark data…")
            try:
                bench_failed, _ = _ensure_batch_cached(
                    tuple(bench_missing),
                    bench_date_start.isoformat(),
                    force_refresh,
                )
                if bench_failed:
                    st.warning(f"Could not download benchmarks: {', '.join(bench_failed)}")
            except Exception as e:
                st.warning(f"Could not download benchmarks: {e}")
            bench_dl.progress(1.0, text="Done")
            bench_dl.empty()
            # Clear benchmark cache so new data is used
            for k in list(st.session_state.keys()):
                if k.startswith("benchmarks_"):
                    del st.session_state[k]

    # ── Compute & cache benchmarks ────────────────────────────────────────────────

    bench_cache_key = f"benchmarks_{base_ccy}_{all_snapshots[0]['date']}_{all_snapshots[-1]['date']}"
    if bench_cache_key not in st.session_state:
        cached = storage.load_benchmarks(base_ccy) if not force_refresh else None
        if (cached and len(cached) == len(all_snapshots)
                and all(k in cached[0] for k in BENCHMARKS.values())):
            st.session_state[bench_cache_key] = cached
        else:
            bench_date_start = date.fromisoformat(all_snapshots[0]["date"])
            bench_date_end = date.fromisoformat(all_snapshots[-1]["date"])
            bench_result: list[dict] = []
            bench_tickers = [b_ticker for b_ticker in BENCHMARKS.values()
                             if any(not storage.has_price_year(b_ticker, y)
                                    or (force_refresh and y == today.year)
                                    for y in range(bench_date_start.year, bench_date_end.year + 1))]
            if bench_tickers:
                ensure_batch(bench_tickers, bench_date_start, bench_date_end,
                             force_refresh_current_year=force_refresh)

            for b_label, b_ticker in BENCHMARKS.items():
                if not any(storage.has_price_year(b_ticker, y)
                           for y in range(bench_date_start.year, bench_date_end.year + 1)):
                    continue

                fx_c: dict = {}
                bp_c: dict = {}
                b_vals: list[float] = []
                cum_units = 0.0
                cum_invested = 0.0
                pending_eur = 0.0

                for snap in all_snapshots:
                    day = snap["date"]
                    yr = int(day[:4])
                    new_inv = snap["invested"] - cum_invested
                    cum_invested = snap["invested"]

                    if base_ccy == "EUR":
                        new_eur = new_inv
                    else:
                        fx_to_eur = get_fx_rate(base_ccy, "EUR", day, fx_c, yr)
                        new_eur = new_inv * fx_to_eur

                    pending_eur += new_eur

                    price = get_price(b_ticker, day, bp_c, yr)
                    if price is None or price <= 0:
                        b_vals.append(b_vals[-1] if b_vals else 0.0)
                        continue

                    cum_units += pending_eur / price
                    pending_eur = 0.0

                    if base_ccy == "EUR":
                        hyp = cum_units * price
                    else:
                        fx_to_base = get_fx_rate("EUR", base_ccy, day, fx_c, yr)
                        hyp = cum_units * price * fx_to_base

                    b_vals.append(round(hyp, 2))

                if not bench_result:
                    bench_result = [{"date": s["date"]} for s in all_snapshots]
                for i, v in enumerate(b_vals):
                    bench_result[i][b_ticker] = v

            storage.save_benchmarks(base_ccy, bench_result)
            st.session_state[bench_cache_key] = bench_result

    all_benchmarks: list[dict] = st.session_state.get(bench_cache_key, [])

    # ── Bench index by date ──────────────────────────────────────────────────────
    bench_by_date: dict[str, dict] = {b["date"]: b for b in all_benchmarks}

    # Filter to chart date range
    chart_start = st.session_state.get("chart_start", data_start_date)
    chart_end = st.session_state.get("chart_end", today)
    cs = chart_start.isoformat()
    ce = chart_end.isoformat()
    snapshots = [s for s in all_snapshots if cs <= s["date"] <= ce]

    # Filter out leading zero-value snapshots (before first transaction)
    first_nonzero = next((i for i, s in enumerate(snapshots) if s["total_value"] != 0.0), None)
    if first_nonzero is not None:
        snapshots = snapshots[first_nonzero:]

    if not snapshots:
        st.warning("No portfolio data for the selected date range. Try 'All time' or add transactions.")
        st.stop()

    dates, values, investeds = snapshots_to_series(snapshots)

    # ── Metric cards ──────────────────────────────────────────────────────────────

    latest = snapshots[-1]
    prev   = snapshots[-2] if len(snapshots) > 1 else None

    cur_value  = latest["total_value"]
    contrib    = latest["invested"]
    pnl        = cur_value - contrib
    pnl_pct    = (pnl / contrib * 100) if contrib else 0.0
    day_change = (cur_value - prev["total_value"]) if prev else 0.0
    day_pct    = (day_change / prev["total_value"] * 100) if prev and prev["total_value"] else 0.0

    SYM = CURRENCY_SYMBOLS

    def _fmt_money(v: float) -> str:
        formatted = f"{v:,.0f}".replace(",", " ")
        if base_ccy == "PLN":
            return f"{formatted} PLN"
        return f"{SYM[base_ccy]}{formatted}"

    fx_cache: dict = {}
    cagr = compute_cagr(cur_value, base_ccy, fx_cache=fx_cache, end=ce)
    irr = compute_irr(cur_value, base_ccy, fx_cache=fx_cache, end=ce)

    best_ticker = max(latest["assets"], key=lambda a: a["value_base"])["ticker"] if latest["assets"] else "—"

    cagr_str = f"{cagr * 100:.1f}%" if cagr is not None else "—"
    irr_str = f"{irr * 100:.1f}%" if irr is not None else "—"

    render_metric_section(T, base_ccy, cur_value, contrib, best_ticker, cagr_str, irr_str, _fmt_money)
    render_pnl_toggle_section(T, pnl, pnl_pct, _fmt_money)

    chart_mode = st.session_state.chart_mode
    render_portfolio_chart(T, base_ccy, dates, values, investeds, bench_by_date, BENCHMARKS, BENCH_COLORS, chart_mode)

    bench_selected_keys = st.multiselect(
        "What-if benchmarks",
        options=list(BENCHMARKS.keys()),
        key="bench_select",
        placeholder="Choose options",
        on_change=lambda: st.session_state.update(bench_persist=list(st.session_state.bench_select)),
    )

    def _show_trade_dialog(ticker: str, name: str, ccy: str):
        render_trade_history_dialog(T, ticker, name, ccy, base_ccy, today, storage)

    # ── Holdings table ────────────────────────────────────────────────────────────

    if latest["assets"]:
        render_holdings_table(
            T,
            latest["assets"],
            base_ccy,
            today,
            storage,
            get_fx_rate,
            get_ticker_name,
            _show_trade_dialog,
        )

        st.subheader("🧩  Allocation Breakdown")
        render_allocation_breakdown(latest["assets"], base_ccy, today, T, get_ticker_meta)

        render_drawdown_analysis(all_snapshots, T)

    # ── Footer ────────────────────────────────────────────────────────────────────

    st.caption(
        f":material/info: Yahoo Finance · {today} · {base_ccy} · "
        f"Daily · {len(latest.get('assets', [])) if latest else 0} positions"
    )

    render_watchlist(T)

    # ── Late-stage theme override (injected last, beats Streamlit's dark CSS) ──
    st.markdown(build_late_theme_override(T), unsafe_allow_html=True)

    # ── JS injection: beat Streamlit's dynamically-injected emotion-cache CSS ──────
    st.iframe(build_streamlit_fix_script(T), height=1, width=1)


