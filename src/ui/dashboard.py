from __future__ import annotations

import time
from datetime import date

import streamlit as st

import storage
from currencies import CURRENCY_SYMBOLS
from portfolio_core import (
    FX_TICKERS,
    _ticker_currency,
    build_portfolio,
    snapshots_to_series,
)
from ticker_data import (
    ensure_batch,
    ensure_parallel,
    get_fx_rate,
    get_price,
    get_ticker_name,
    get_ticker_meta,
)
from ledger_core import (
    annualize_twr,
    compute_irr,
    compute_twr,
    get_all_tickers,
    get_all_transactions,
)
from datetime import timedelta
from ui.holdings import render_holdings_table
from ui.allocation import render_allocation_breakdown
from ui.metrics import render_metric_section
from ui.colors import BENCHMARKS, BENCH_COLORS
from ui.portfolio_chart import render_portfolio_chart, render_benchmarking_section
from ui.styles import (
    build_late_theme_override,
    build_streamlit_fix_script,
    render_empty_state,
    render_project_banner,
)
from ui.trade_history import render_trade_history_dialog
from ui.watchlist import render_watchlist


@st.cache_data(ttl=3600)
def _ensure_parallel_cached(
    tickers_tuple: tuple[str, ...],
    start_date_iso: str,
) -> list[str]:
    """Cached parallel price download — reruns skip re-downloading within a session.

    Uses ensure_parallel (ThreadPoolExecutor) so multiple tickers download
    concurrently. The caller pre-filters `tickers_tuple` to only tickers that
    actually need downloading, so no force_refresh flag is needed here.
    Returns failed tickers.
    """
    return ensure_parallel(
        list(tickers_tuple),
        date.fromisoformat(start_date_iso),
        force_refresh_current_year=True,
    )


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
        _ensure_parallel_cached.clear()

    # Check which tickers actually need downloading across entire transaction history
    start_year = data_start_date.year
    missing = [
        t for t in tickers_needed
        if t not in storage.SUPPORTED_CURRENCIES
        and (
            force_refresh
            or any(not storage.has_price_year(t, y) for y in range(start_year, today.year + 1))
        )
    ]

    download_errors: list[str] = []

    if missing:
        dl_bar = st.progress(0, text=f"Downloading {len(missing)} tickers…")

        try:
            download_errors = _ensure_parallel_cached(
                tuple(missing),
                data_start_date.isoformat(),
            )
        except Exception as e:
            download_errors = list(missing)
            st.caption(f"⚠ Download failed: {e}")

        dl_bar.empty()

        if download_errors:
            st.warning(
                f"⚠️ Could not download price data for: **{', '.join(download_errors)}**\n\n"
                "These positions will be missing from the chart. "
                "Check your internet connection and try **Refresh data**."
            )

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

    if not all_snapshots:
        st.warning("No portfolio data available yet. Transactions may all be future-dated.")
        st.stop()

    # ── Download data for selected benchmarks ─────────────────────────────────────
    # Benchmarks use the ADJUSTED (total-return) cache: the portfolio earns
    # dividends as cash, so a fair what-if comparison needs the benchmark's
    # dividends too. Everything else in the app uses the RAW price cache.
    bench_persist = st.session_state.get("bench_persist", [])
    if bench_persist:
        bench_date_start = date.fromisoformat(all_snapshots[0]["date"])
        bench_date_end = date.fromisoformat(all_snapshots[-1]["date"])
        bench_tickers_needed = [BENCHMARKS[k] for k in bench_persist if k in BENCHMARKS]
        bench_missing = [
            t for t in bench_tickers_needed
            if t not in storage.SUPPORTED_CURRENCIES
            and (force_refresh or not storage.has_price_year(t, today.year, adjusted=True))
        ]
        if bench_missing:
            bench_dl = st.progress(0, text="Downloading benchmark data…")
            try:
                bench_failed = ensure_batch(
                    bench_missing,
                    bench_date_start,
                    bench_date_end,
                    force_refresh_current_year=force_refresh,
                    adjusted=True,
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
                             if any(not storage.has_price_year(b_ticker, y, adjusted=True)
                                    or (force_refresh and y == today.year)
                                    for y in range(bench_date_start.year, bench_date_end.year + 1))]
            if bench_tickers:
                ensure_batch(bench_tickers, bench_date_start, bench_date_end,
                             force_refresh_current_year=force_refresh, adjusted=True)

            for b_label, b_ticker in BENCHMARKS.items():
                if not any(storage.has_price_year(b_ticker, y, adjusted=True)
                           for y in range(bench_date_start.year, bench_date_end.year + 1)):
                    continue

                # Benchmarks may be quoted in a non-EUR currency (e.g. the
                # US-listed SMH in USD vs Xetra ETFs in EUR).
                bench_ccy = _ticker_currency(b_ticker)

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

                    price = get_price(b_ticker, day, bp_c, yr, adjusted=True)
                    if price is None or price <= 0:
                        b_vals.append(b_vals[-1] if b_vals else 0.0)
                        continue

                    # Convert non-EUR benchmark closes to EUR so the
                    # hypothetical purchase is always made in EUR.
                    if bench_ccy != "EUR":
                        price *= get_fx_rate(bench_ccy, "EUR", day, fx_c, yr)

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

    project_name = storage.active_project() if hasattr(storage, "active_project") else "Portfel"
    if project_name == "default":
        project_name = "Portfel inwestycyjny"

    # ── Filter out leading zero-value snapshots ──────────────────────────────────
    first_nonzero = next((i for i, s in enumerate(all_snapshots) if s["total_value"] != 0.0), 0)
    active_snapshots = all_snapshots[first_nonzero:]
    if not active_snapshots:
        st.warning("Brak aktywnych pozycji w wybranym portfelu.")
        st.stop()

    min_portfolio_date = date.fromisoformat(active_snapshots[0]["date"])

    # ── Top Metric Cards (FundStat 3-Card Design) ────────────────────────────────
    latest = active_snapshots[-1]
    cur_value = float(latest["total_value"])
    contrib = float(latest["invested"])
    pnl = cur_value - contrib
    pnl_pct = (pnl / contrib * 100) if contrib else 0.0

    SYM = CURRENCY_SYMBOLS

    def _fmt_money(v: float) -> str:
        formatted = f"{v:,.0f}".replace(",", " ")
        if base_ccy == "PLN":
            return f"{formatted} zł"
        elif base_ccy == "USD":
            return f"{formatted} USD"
        elif base_ccy == "EUR":
            return f"{formatted} €"
        return f"{formatted} {base_ccy}"

    fx_cache: dict = {}
    ce_all = active_snapshots[-1]["date"]
    twr_cum = float(latest.get("twr", 0.0))
    if twr_cum == 0.0 and len(active_snapshots) > 1:
        twr_cum = compute_twr(active_snapshots, base_ccy, fx_cache=fx_cache, end=ce_all) or 0.0

    irr = compute_irr(cur_value, base_ccy, fx_cache=fx_cache, end=ce_all)
    span_days = max((date.fromisoformat(active_snapshots[-1]["date"]) - min_portfolio_date).days, 1)
    twr_ann = annualize_twr(twr_cum, span_days) if twr_cum else None

    twr_cum_str = f"{twr_cum * 100:+.2f}%"
    twr_ann_str = f"{twr_ann * 100:+.2f}%" if twr_ann is not None else "—"
    mwr_cum_str = f"{pnl_pct:+.2f}%"
    mwr_ann_str = f"{irr * 100:+.2f}%" if irr is not None else "—"

    best_ticker = max(latest["assets"], key=lambda a: a["value_base"])["ticker"] if latest["assets"] else "—"

    render_metric_section(
        T,
        base_ccy=base_ccy,
        cur_value=cur_value,
        contrib=contrib,
        best_ticker=best_ticker,
        fmt=_fmt_money,
        pnl=pnl,
        pnl_pct=pnl_pct,
        twr_cum_str=twr_cum_str,
        twr_ann_str=twr_ann_str,
        mwr_cum_str=mwr_cum_str,
        mwr_ann_str=mwr_ann_str,
    )

    # ── Section 1: Portfel w czasie (Main Chart) ──────────────────────────────────
    # Date range filtered strictly from sidebar's Range dropdown
    chart_start = st.session_state.get("chart_start", min_portfolio_date)
    chart_end = st.session_state.get("chart_end", today)
    cs = chart_start.isoformat()
    ce = chart_end.isoformat()
    chart_snapshots = [s for s in active_snapshots if cs <= s["date"] <= ce] or active_snapshots

    if "portfolio_chart_mode" not in st.session_state:
        st.session_state["portfolio_chart_mode"] = "value"

    st.markdown(
        f"""
        <div class="section-header-box" style="margin-top:1.5rem;">
          <div class="section-title">Portfel w czasie</div>
          <div class="section-date-badge">{chart_snapshots[0]['date']} – {chart_snapshots[-1]['date']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Chart Mode Tabs
    mode_tabs = [
        ("value", "Wartość portfela"),
        ("profit", "Zysk całkowity"),
        ("twr", "TWR"),
        ("mwr", "MWR"),
        ("drawdown", "Obsunięcie"),
    ]
    active_chart_mode = st.session_state["portfolio_chart_mode"]
    m_cols = st.columns(len(mode_tabs))
    for col, (m_key, m_label) in zip(m_cols, mode_tabs):
        with col:
            is_active = (m_key == active_chart_mode)
            if st.button(m_label, key=f"p_mode_{m_key}", type="primary" if is_active else "secondary", width="stretch"):
                st.session_state["portfolio_chart_mode"] = m_key
                st.rerun()

    log_scale = bool(st.session_state.get("log_scale", False))
    render_portfolio_chart(
        T,
        base_ccy=base_ccy,
        snapshots=chart_snapshots,
        bench_by_date=bench_by_date,
        benchmarks=BENCHMARKS,
        bench_colors=BENCH_COLORS,
        chart_mode=active_chart_mode,
        log_scale=log_scale,
    )

    # ── Section 2: Benchmarking ──────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="section-header-box" style="margin-top:2rem;">
          <div class="section-title">Benchmarking</div>
          <div class="section-date-badge">{chart_snapshots[0]['date']} – {chart_snapshots[-1]['date']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "bench_chart_mode" not in st.session_state:
        st.session_state["bench_chart_mode"] = "twr"
    active_bench_mode = st.session_state["bench_chart_mode"]

    bench_mode_tabs = [
        ("twr", "TWR"),
        ("mwr", "MWR"),
        ("value", "Wartość portfela"),
        ("profit", "Zysk całkowity"),
    ]
    b_cols = st.columns(len(bench_mode_tabs))
    for col, (b_key, b_label) in zip(b_cols, bench_mode_tabs):
        with col:
            is_active = (b_key == active_bench_mode)
            if st.button(b_label, key=f"b_mode_{b_key}", type="primary" if is_active else "secondary", width="stretch"):
                st.session_state["bench_chart_mode"] = b_key
                st.rerun()

    bench_selected_keys = st.multiselect(
        "Wybierz benchmarki do porównania",
        options=list(BENCHMARKS.keys()),
        default=st.session_state.get("bench_persist", list(BENCHMARKS.keys())[:2]),
        key="bench_select",
        on_change=lambda: st.session_state.update(bench_persist=list(st.session_state.bench_select)),
    )

    render_benchmarking_section(
        T,
        base_ccy=base_ccy,
        snapshots=chart_snapshots,
        bench_by_date=bench_by_date,
        benchmarks=BENCHMARKS,
        bench_colors=BENCH_COLORS,
        bench_mode=active_bench_mode,
        project_name=project_name,
    )

    def _show_trade_dialog(ticker: str, name: str, ccy: str):
        render_trade_history_dialog(T, ticker, name, ccy, base_ccy, today, storage)

    # ── Section 3: Holdings Table (Aktywa) ─────────────────────────────────────────
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

    # ── Footer ────────────────────────────────────────────────────────────────────
    render_watchlist(T)

    # ── Late-stage theme override (injected last, beats Streamlit's dark CSS) ──
    st.markdown(build_late_theme_override(T), unsafe_allow_html=True)

    # ── JS injection: beat Streamlit's dynamically-injected emotion-cache CSS ──────
    st.iframe(build_streamlit_fix_script(T), height=1, width=1)


