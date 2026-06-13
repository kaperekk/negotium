"""
app.py —  Negotium - Investment Tracker UI (Streamlit)

Run: streamlit run src/app.py
"""
from __future__ import annotations

import sys
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import date, timedelta

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg_module
import storage
from ticker_data import ensure as ensure_ticker, get_price, get_fx_rate
from portfolio import FX_TICKERS
from transactions import (
    add_transaction, get_all_transactions, get_all_tickers,
    set_account_operation, delete_transaction, update_transaction,
)
from portfolio import build_portfolio, snapshots_to_series
from xtb_import import import_xtb
from bossa_import import import_bossa
from manual_import import import_manual

IMPORTS_DIR = Path("imports")
BROKERS = ["XTB", "BOSSA", "Custom"]
BROKER_CURRENCIES = {"XTB": ["EUR", "PLN", "USD"], "BOSSA": ["EUR", "PLN", "Many"]}


def _detect_currency(filename: str) -> str:
    prefix = filename.strip()[:3].upper()
    return prefix if prefix in ("EUR", "PLN", "USD") else "USD"

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Negotium",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* ── Metric cards ──────────────────────────────────────────────────── */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #161B22 0%, #1C2333 100%);
        border: 1px solid #30363D;
        border-radius: 16px;
        padding: 20px 24px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    [data-testid="metric-container"] label {
        font-size: 0.75rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.08em !important;
        color: #8B949E !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-weight: 700 !important;
    }

    /* ── Sidebar ───────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        min-width: 380px;
        max-width: 420px;
        border-right: 1px solid #30363D;
    }

    /* ── Expanders ─────────────────────────────────────────────────────── */
    details[data-testid="stExpander"] {
        background: #161B22;
        border: 1px solid #30363D;
        border-radius: 12px;
    }

    /* ── Dividers ──────────────────────────────────────────────────────── */
    hr { border-color: #21262D !important; }

    /* ── DataFrame ─────────────────────────────────────────────────────── */
    [data-testid="stDataFrame"] {
        border: 1px solid #30363D;
        border-radius: 12px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

# ── Config ────────────────────────────────────────────────────────────────────

cfg            = cfg_module.load()
start_date_cfg = cfg_module.get_start_date(cfg)
today          = date.today()

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title(f"📈 {cfg.get('name', 'My Portfolio')}")
    st.divider()

    st.subheader("Display")
    base_ccy = st.selectbox(
        "Base currency",
        options=["PLN", "EUR", "USD"],
        index=["PLN", "EUR", "USD"].index(cfg.get("default_currency", "PLN")),
    )

    precision = "D"

    st.subheader("Date range")
    range_option = st.selectbox(
        "Quick range",
        ["All time", "This year", "Last 12 months", "Last 3 months", "Custom"],
    )
    if range_option == "All time":
        chart_start, chart_end = start_date_cfg, today
    elif range_option == "This year":
        chart_start, chart_end = date(today.year, 1, 1), today
    elif range_option == "Last 12 months":
        chart_start, chart_end = today - timedelta(days=365), today
    elif range_option == "Last 3 months":
        chart_start, chart_end = today - timedelta(days=90), today
    else:
        ca, cb = st.columns(2)
        with ca:
            chart_start = st.date_input("From", value=start_date_cfg,
                                        min_value=start_date_cfg, max_value=today)
        with cb:
            chart_end = st.date_input("To", value=today,
                                      min_value=start_date_cfg, max_value=today)

    st.divider()

    with st.expander("⚙️ Settings"):
        new_name  = st.text_input("Portfolio name", value=cfg.get("name", "My Portfolio"))
        new_start = st.date_input("Start date", value=start_date_cfg, max_value=today)
        new_ccy   = st.selectbox("Default currency", ["PLN", "EUR", "USD"],
                                 index=["PLN", "EUR", "USD"].index(cfg.get("default_currency", "PLN")))
        if st.button("Save settings"):
            cfg.update({"name": new_name, "start_day": new_start.isoformat(),
                        "default_currency": new_ccy})
            cfg_module.save(cfg)
            for k in list(st.session_state.keys()):
                if k.startswith("snapshots_"):
                    del st.session_state[k]
            st.success("Saved!")
            st.rerun()

        st.divider()
        st.subheader("Ticker rules")
        rules_text = st.text_area(
            "Rules",
            value="\n".join(cfg.get("ticker_rules", [])),
            height=200,
            key="ticker_rules_text",
            label_visibility="collapsed",
            placeholder="AMZN.DE=AMZ.DE\n*.PL=*.WA\n.US=",
        )
        if st.button("Save ticker rules"):
            new_rules = [line.strip() for line in rules_text.strip().splitlines() if line.strip()]
            cfg["ticker_rules"] = new_rules
            cfg_module.save(cfg)
            st.success("Rules saved!")
            st.rerun()

    st.divider()

    with st.expander("➕ Add transaction"):
        with st.form("add_tx", clear_on_submit=True):
            tx_date = st.date_input("Date", value=today, max_value=today)
            st.caption("Negative amount = sell / cash out.")

            rows = []
            for idx in range(1, 4):
                c1, c2 = st.columns([2, 1])
                with c1:
                    t = st.text_input(
                        f"Ticker {idx}",
                        placeholder="AAPL / QDVE.DE / USD / PLN",
                        key=f"t{idx}",
                    ).strip().upper()
                with c2:
                    a = st.number_input(f"Amount {idx}", value=0.0,
                                        format="%.4f", step=0.001, key=f"a{idx}")
                rows.append((t, a))

            is_account_op = st.checkbox("Account operation (deposit/withdrawal)",
                                        key="ao_new",
                                        help="Marks this transaction as invested capital")

            if st.form_submit_button("Add transaction", width="stretch"):
                entries = [{"ticker": t, "amount": a,
                            **({"account_operation": True} if is_account_op else {})}
                           for t, a in rows if t and abs(a) > 1e-9]
                if not entries:
                    st.error("Enter at least one ticker and amount.")
                else:
                    custom_dir = IMPORTS_DIR / "custom"
                    custom_dir.mkdir(parents=True, exist_ok=True)
                    tx_doc = [{"date": tx_date.isoformat(), "entries": entries}]
                    tx_path = custom_dir / f"{tx_date.isoformat()}_{tx_date.strftime('%H%M%S')}.json"
                    tx_path.write_text(json.dumps(tx_doc, indent=2), encoding="utf-8")
                    result = import_manual(str(tx_path))
                    if result["success"]:
                        st.success(f"Added for {tx_date}.")
                    else:
                        st.error(result["error"])
                    st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
                    st.rerun()

    st.divider()

    with st.expander("📥 Import statement"):
        IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

        broker = st.selectbox("Broker", BROKERS, key="broker_select")
        broker_dir = IMPORTS_DIR / broker.lower()
        broker_dir.mkdir(parents=True, exist_ok=True)

        file_types = ["csv"] if broker == "BOSSA" else ["json"] if broker == "Custom" else ["xlsx"]
        uploaded_files = st.file_uploader(
            f"Upload {broker} files", type=file_types,
            accept_multiple_files=True, key="xtb_upload",
            label_visibility="collapsed",
        )

        for uf in uploaded_files:
            dest = broker_dir / uf.name
            if not dest.exists():
                dest.write_bytes(uf.getvalue())

        broker_files = sorted(broker_dir.glob("*.xlsx")) + sorted(broker_dir.glob("*.csv")) + sorted(broker_dir.glob("*.json"))

        if broker_files:
            for fpath in broker_files:
                detected = _detect_currency(fpath.name)
                if broker == "BOSSA":
                    ccy = "Many"
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.caption(f"📄 {fpath.name} (currency: auto)")
                    with c2:
                        if st.button("⬇", key=f"imp_{broker}_{fpath.name}",
                                     help="Import this file"):
                            if fpath.suffix.lower() == ".csv":
                                with st.spinner("Importing…"):
                                    result = import_bossa(str(fpath), ccy)
                            else:
                                result = import_xtb(str(fpath), ccy)
                            if result["success"]:
                                n = result["imported"]
                                s = result["skipped"]
                                msg = f"**{fpath.name}** — {n} imported"
                                if s:
                                    msg += f", {s} skipped (duplicates)"
                                st.success(msg)
                                st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
                                st.rerun()
                            else:
                                st.error(f"**{fpath.name}** — {result['error']}")
                elif broker == "Custom":
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.caption(f"📄 {fpath.name}")
                    with c2:
                        if st.button("⬇", key=f"imp_{broker}_{fpath.name}",
                                     help="Import this file"):
                            result = import_manual(str(fpath))
                            if result["success"]:
                                n = result["imported"]
                                s = result["skipped"]
                                msg = f"**{fpath.name}** — {n} imported"
                                if s:
                                    msg += f", {s} skipped (duplicates)"
                                st.success(msg)
                                st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
                                st.rerun()
                            else:
                                st.error(f"**{fpath.name}** — {result['error']}")
                else:
                    ccy_options = BROKER_CURRENCIES.get(broker, ["EUR", "PLN", "USD"])
                    default_ccy = ccy_options[0]
                    if detected not in ccy_options:
                        detected = default_ccy
                    c1, c2, c3 = st.columns([2, 2, 1])
                    with c1:
                        st.caption(f"📄 {fpath.name}")
                    with c2:
                        ccy = st.selectbox(
                            "Currency", ccy_options,
                            index=ccy_options.index(detected),
                            key=f"ccy_{broker}_{fpath.name}",
                            label_visibility="collapsed",
                        )
                    with c3:
                        if st.button("⬇", key=f"imp_{broker}_{fpath.name}",
                                     help="Import this file"):
                            if ccy != detected:
                                new_name = f"{ccy}_{fpath.name}"
                                new_path = broker_dir / new_name
                                fpath.rename(new_path)
                                fpath = new_path
                            result = import_xtb(str(fpath), ccy)
                            if result["success"]:
                                n = result["imported"]
                                s = result["skipped"]
                                msg = f"**{fpath.name}** — {n} imported"
                                if s:
                                    msg += f", {s} skipped (duplicates)"
                                st.success(msg)
                                st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
                                st.rerun()
                            else:
                                st.error(f"**{fpath.name}** — {result['error']}")
        else:
            st.caption("No files uploaded yet.")

        if st.button("♻️  Rebuild from ALL imports", width="stretch"):
            for p in [storage.TRANSACTIONS_PATH, storage.PORTFOLIO_PATH, storage.BALANCE_PATH]:
                p.write_text("")

            all_files = []
            for b in BROKERS:
                bdir = IMPORTS_DIR / b.lower()
                if not bdir.exists():
                    continue
                for fpath in sorted(bdir.glob("*.xlsx")):
                    all_files.append(("xtb", fpath))
                for fpath in sorted(bdir.glob("*.csv")):
                    all_files.append(("bossa", fpath))

            if all_files:
                bar = st.progress(0, text="Importing…")
                total_imported = 0
                for idx, (kind, fpath) in enumerate(all_files):
                    ccy = _detect_currency(fpath.name)
                    bar.progress(idx / len(all_files), text=f"Importing {fpath.name}…")
                    if kind == "bossa":
                        result = import_bossa(str(fpath), ccy)
                    else:
                        result = import_xtb(str(fpath), ccy)
                    if result["success"]:
                        total_imported += result["imported"]
                bar.progress(1.0, text="Done")
                bar.empty()
            else:
                total_imported = 0

            st.success(f"Rebuilt from {len(all_files)} files — {total_imported} transactions imported.")
            st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
            st.rerun()

    if st.button("📈  Refresh market data", width="stretch"):
        st.session_state.pop(f"snapshots_{base_ccy}_{precision}", None)
        st.session_state["force_refresh"] = True
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

st.header(cfg.get("name", "My Portfolio"))

all_tx = get_all_transactions()
if not all_tx:
    st.info("No transactions yet — add your first one using the sidebar form.")
    st.caption("Example: Ticker 1 = `AAPL`, Amount 1 = `10` / Ticker 2 = `USD`, Amount 2 = `-1700`")
    st.stop()

# ── Market data download ──────────────────────────────────────────────────────

tickers_needed = get_all_tickers(include_fx=True)
force_refresh  = st.session_state.pop("force_refresh", False)

# Check which tickers actually need downloading
missing = [
    t for t in tickers_needed
    if t not in storage.SUPPORTED_CURRENCIES
    and (force_refresh or not storage.has_price_year(t, today.year))
]

download_errors: list[str] = []

if missing:
    dl_bar     = st.progress(0)
    dl_status  = st.empty()

    results: dict[str, bool] = {}

    def _fetch(ticker: str) -> tuple[str, bool, str]:
        try:
            ensure_ticker(ticker, start_date=start_date_cfg,
                          force_refresh_current_year=True)
            return ticker, True, ""
        except Exception as e:
            return ticker, False, str(e)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch, t): t for t in missing}
        done = 0
        for future in as_completed(futures):
            ticker, ok, err = future.result()
            done += 1
            dl_bar.progress(done / len(missing))
            if ok:
                dl_status.caption(f"✓ Downloaded {ticker}")
            else:
                dl_status.caption(f"⚠ {ticker}: {err}")
                download_errors.append(ticker)

    dl_bar.empty()
    dl_status.empty()

    if download_errors:
        st.warning(
            f"⚠️ Could not download price data for: **{', '.join(download_errors)}**\n\n"
            "These positions will be missing from the chart. "
            "Check your internet connection and try **Refresh market data**."
        )

# Warn if we have stock tickers but zero price files at all
stock_tickers = [t for t in tickers_needed
                 if t not in storage.SUPPORTED_CURRENCIES and t not in FX_TICKERS]
tickers_with_data = [t for t in stock_tickers if storage.has_price_year(t, today.year)
                     or any(storage.has_price_year(t, y) for y in range(start_date_cfg.year, today.year + 1))]
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
        start_date=start_date_cfg,
        end_date=today,
        base_currency=base_ccy,
        precision=precision,
        progress_cb=_on_progress,
        use_cache=True,
    )
    elapsed = time.perf_counter() - t_start
    bar.empty()

    log_path = Path(__file__).parent.parent / "data" / "build.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{today.isoformat()} {time.strftime('%H:%M:%S')} | "
                f"{base_ccy} {precision} | {elapsed:.3f}s | "
                f"{len(all_snapshots)} snapshots\n")

    st.session_state[cache_key] = all_snapshots

all_snapshots: list[dict] = st.session_state[cache_key]

BENCHMARKS = {
    "NASDAQ 100 (SXRV.DE)": "SXRV.DE",
    "S&P 500 (I500.DE)": "I500.DE",
    "Emerging Markets (IS3N.DE)": "IS3N.DE",
    "Bitcoin (BTCE.DE)": "BTCE.DE",
    "Gold (4GLD.DE)": "4GLD.DE",
}
BENCH_COLORS = {
    "NASDAQ 100 (SXRV.DE)": "#06b6d4",
    "S&P 500 (I500.DE)": "#22c55e",
    "Emerging Markets (IS3N.DE)": "#8b5cf6",
    "Bitcoin (BTCE.DE)": "#ef4444",
    "Gold (4GLD.DE)": "#eab308",
}

# ── Compute & cache benchmarks ────────────────────────────────────────────────

bench_cache_key = f"benchmarks_{base_ccy}_{len(all_snapshots)}"
if bench_cache_key not in st.session_state:
    cached = storage.load_benchmarks(base_ccy)
    if cached and len(cached) == len(all_snapshots):
        st.session_state[bench_cache_key] = cached
    else:
        bench_date_start = date.fromisoformat(all_snapshots[0]["date"])
        bench_date_end = date.fromisoformat(all_snapshots[-1]["date"])
        bench_result: list[dict] = []

        for b_label, b_ticker in BENCHMARKS.items():
            try:
                ensure_ticker(b_ticker, bench_date_start, bench_date_end,
                              force_refresh_current_year=False)
            except Exception:
                continue

            fx_c: dict = {}
            bp_c: dict = {}
            b_vals: list[float] = []
            cum_units = 0.0
            prev_inv = 0.0

            for snap in all_snapshots:
                day = snap["date"]
                yr = int(day[:4])
                new_inv = snap["invested"] - prev_inv
                prev_inv = snap["invested"]

                price = get_price(b_ticker, day, bp_c, yr)
                if price is None or price <= 0:
                    b_vals.append(b_vals[-1] if b_vals else 0.0)
                    continue

                if base_ccy == "EUR":
                    new_eur = new_inv
                else:
                    fx_to_eur = get_fx_rate(base_ccy, "EUR", day, fx_c, yr)
                    new_eur = new_inv * fx_to_eur

                cum_units += new_eur / price

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

show_invested = st.session_state.get("show_invested", False)

bench_selected = {
    label: st.session_state.get("bench_select", []) and label in st.session_state.get("bench_select", [])
    for label in BENCHMARKS
}

# ── Metric cards ──────────────────────────────────────────────────────────────

latest = snapshots[-1]
prev   = snapshots[-2] if len(snapshots) > 1 else None

cur_value  = latest["total_value"]
contrib    = latest["invested"]
pnl        = cur_value - contrib
pnl_pct    = (pnl / contrib * 100) if contrib else 0.0
day_change = (cur_value - prev["total_value"]) if prev else 0.0
day_pct    = (day_change / prev["total_value"] * 100) if prev and prev["total_value"] else 0.0

SYM = {"PLN": " PLN", "EUR": "€", "USD": "$"}

def fmt(v: float) -> str:
    formatted = f"{v:,.0f}".replace(",", " ")
    if base_ccy == "PLN":
        return f"{formatted} PLN"
    return f"{SYM[base_ccy]}{formatted}"

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total value", fmt(cur_value))
with c2:
    st.metric("Invested", fmt(contrib))
with c3:
    sign = "+" if pnl >= 0 else ""
    st.metric("Total P&L", f"{sign}{fmt(pnl)}", delta=f"{sign}{pnl_pct:.1f}%")
with c4:
    if latest["assets"]:
        best = max(latest["assets"], key=lambda a: a["value_base"])
        st.metric("Largest position", best["ticker"])
    else:
        st.metric("Largest position", "—")

st.divider()

# ── Chart ─────────────────────────────────────────────────────────────────────

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=dates, y=values,
    name=f"Portfolio ({base_ccy})",
    fill="tozeroy",
    line=dict(color="#6C63FF", width=2.5),
    fillcolor="rgba(108,99,255,0.08)",
    hovertemplate="%{x|%d %b %Y}<br><b>%{y:,.0f} " + base_ccy + "</b><extra></extra>",
))
if show_invested:
    fig.add_trace(go.Scatter(
        x=dates, y=investeds,
        name="Invested capital",
        line=dict(color="#94a3b8", width=1.5, dash="dot"),
        hovertemplate="%{x|%d %b %Y}<br>Invested: %{y:,.0f} " + base_ccy + "<extra></extra>",
    ))

for bench_label, bench_ticker in BENCHMARKS.items():
    if not bench_selected.get(bench_label):
        continue

    bench_vals = [bench_by_date.get(d, {}).get(bench_ticker, 0.0) for d in dates]
    fig.add_trace(go.Scatter(
        x=dates, y=bench_vals,
        name=bench_label,
        line=dict(color=BENCH_COLORS[bench_label], width=1.5, dash="dot"),
        hovertemplate=f"%{{x|%d %b %Y}}<br>{bench_label}: %{{y:,.0f}} " + base_ccy + "<extra></extra>",
    ))

fig.update_layout(
    height=450,
    margin=dict(l=0, r=0, t=16, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        font=dict(size=12, color="#8B949E"),
    ),
    xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=11, color="#8B949E")),
    yaxis=dict(
        showgrid=True, gridcolor="rgba(48,54,61,0.6)",
        zeroline=False, tickfont=dict(size=11, color="#8B949E"), tickformat=",.0f",
        ticksuffix=f" {base_ccy}" if base_ccy == "PLN" else "",
        tickprefix="" if base_ccy == "PLN" else SYM[base_ccy],
    ),
    hovermode="x unified",
    font=dict(family="sans-serif"),
)
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

c_inv, c_bench = st.columns([1, 2])
with c_inv:
    st.checkbox("Show invested capital", value=show_invested, key="show_invested")
with c_bench:
    st.multiselect(
        "What-if benchmarks",
        options=list(BENCHMARKS.keys()),
        key="bench_select",
    )

# ── Holdings table ────────────────────────────────────────────────────────────

if latest["assets"]:
    st.subheader("Current holdings")
    total_val = latest["total_value"] or 1.0
    bal = storage.load_balance()

    # avg_price is stored in default_currency; convert to current base_ccy
    cfg_ccy = cfg.get("default_currency", "PLN")
    avg_fx_cache: dict = {}
    avg_fx = get_fx_rate(cfg_ccy, base_ccy, today.isoformat(), avg_fx_cache, today.year) if cfg_ccy != base_ccy else 1.0

    rows = []
    for a in sorted(latest["assets"], key=lambda x: x["value_base"], reverse=True):
        ticker = a["ticker"]
        shares = a["amount"]
        value = a["value_base"]
        avg_raw = bal.get(ticker, {}).get("avg_price", 0.0)
        avg = avg_raw * avg_fx
        cost_basis = shares * avg
        ret_pct = ((value / cost_basis) - 1) * 100 if cost_basis else 0.0
        rows.append({
            "ticker": ticker,
            "ccy": a.get("currency", "—"),
            "weight": value / total_val * 100,
            "shares": shares,
            "value": value,
            "ret_pct": ret_pct,
        })

    def _fmt_val(v: float) -> str:
        s = f"{v:,.0f}".replace(",", " ")
        return f"{SYM.get(base_ccy, '')}{s}" if base_ccy != "PLN" else f"{s} PLN"

    def _fmt_ret(p: float) -> str:
        return f"{p:+.1f}%"

    def _ret_color(p: float) -> str:
        return "#3fb950" if p >= 0 else "#f85149"

    max_weight = max((r["weight"] for r in rows), default=1) or 1

    header = (
        "<tr>"
        "<th>Ticker</th><th>CCY</th><th>Weight</th>"
        "<th>Shares</th><th>Value</th><th>Return %</th>"
        "</tr>"
    )
    body_rows = []
    for r in rows:
        bar_pct = r["weight"]
        bar_color = "#6C63FF"
        ret_col = _ret_color(r["ret_pct"])
        body_rows.append(
            "<tr>"
            f"<td class='ticker-cell'>"
            f"<div class='ticker-bar' style='width:{bar_pct / max_weight * 100:.1f}%;background:{bar_color};'></div>"
            f"<span class='ticker-text'>{r['ticker']}</span>"
            f"</td>"
            f"<td>{r['ccy']}</td>"
            f"<td class='num'>{r['weight']:.1f}%</td>"
            f"<td class='num'>{r['shares']:.4f}</td>"
            f"<td class='num'>{_fmt_val(r['value'])}</td>"
            f"<td class='num' style='color:{ret_col};font-weight:600'>{_fmt_ret(r['ret_pct'])}</td>"
            "</tr>"
        )

    table_html = f"""
    <style>
    .holdings-table {{ width:100%; border-collapse:collapse; font-size:0.88rem; }}
    .holdings-table th {{
        text-align:left; padding:10px 14px; font-weight:600; font-size:0.72rem;
        text-transform:uppercase; letter-spacing:0.06em; color:#8B949E;
        border-bottom:1px solid #30363D;
    }}
    .holdings-table td {{ padding:10px 14px; border-bottom:1px solid #21262D; color:#C9D1D9; }}
    .holdings-table tr:hover td {{ background:rgba(108,99,255,0.06); }}
    .holdings-table .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
    .ticker-cell {{ position:relative; overflow:hidden; }}
    .ticker-bar {{
        position:absolute; top:0; left:0; height:100%; opacity:0.10;
        border-radius:4px; transition:width 0.3s ease;
    }}
    .ticker-text {{ position:relative; font-weight:600; color:#E6EDF3; }}
    </style>
    <table class="holdings-table">
    <thead>{header}</thead>
    <tbody>{"".join(body_rows)}</tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────

st.caption(
    f":material/info: Yahoo Finance · {today} · {base_ccy} · "
    f"Daily · {len(latest.get('assets', [])) if latest else 0} positions"
)

# ── Danger zone ──────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    """
    <style>
    div[data-testid="stButton"] > button[kind="primary"] {
        background-color: #dc3545;
        color: white;
        font-weight: bold;
        border: none;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background-color: #c82333;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
_, center, _ = st.columns([1, 2, 1])
with center:
    if st.button(
        "Remove all transactions, portfolio and balance",
        type="primary",
        key="nuke_all",
    ):
        for path in [storage.TRANSACTIONS_PATH, storage.PORTFOLIO_PATH, storage.BALANCE_PATH]:
            if path.exists():
                path.unlink()
        st.session_state.clear()
        st.rerun()
