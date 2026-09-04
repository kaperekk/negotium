"""Regression tests for the range-vs-refresh bug (AppTest integration).

Reproduces the user-reported scenario end-to-end:
  1. select "Last 3 months" in the sidebar
  2. click "Refresh data" (which re-imports broker files)
  3. the chart must STILL show only the selected range — not the full history

Also guards against the StreamlitDuplicateElementId crash caused by multiple
st.plotly_chart calls sharing an auto-generated ID (allocation donuts vs
drawdown chart).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

WRAPPER_APP = '''\
import sys
from pathlib import Path

REPO = Path({repo!r})
TMP = Path({tmp!r})
sys.path.insert(0, str(REPO / "src"))

import streamlit as st

import storage
import config as cfg_module

storage.ROOT = TMP
storage.DATA_ROOT = TMP / "data"
storage.PRICES_DIR = TMP / "data" / "prices"
storage.PROJECTS_PATH = TMP / "data" / "projects.json"
cfg_module.ROOT = TMP
cfg_module.GLOBAL_CONFIG_PATH = TMP / "data" / "config.json"

import ledger_core
from ui.dashboard import render_dashboard
from ui.helpers import detect_currency
from ui.runtime import init_runtime
from ui.sidebar import render_sidebar
from ui.styles import build_app_styles

# Stub network — the regression test must never touch Yahoo Finance
import ui.dashboard as _d
import ticker_data as _td

_d.ensure_batch = lambda *a, **k: []
_td.ensure = lambda *a, **k: None
_td.get_ticker_name = lambda t: t
_td.get_ticker_meta = lambda t: {{"sector": "X", "country": "US", "asset_class": "Equity"}}

st.set_page_config(page_title="Negotium", page_icon="\\u26a1", layout="wide")

cfg, storage, _theme_name, T, today = init_runtime()
st.markdown(build_app_styles(T), unsafe_allow_html=True)
data_start_date = ledger_core.first_transaction_date() or today
base_ccy = render_sidebar(cfg, storage, T, today, data_start_date, detect_currency)
render_dashboard(cfg, storage, T, today, data_start_date, base_ccy)
'''


def _build_temp_app(tmp_path: Path) -> Path:
    """Create an isolated data root with a 2-year ledger + broker file to re-import."""
    data = tmp_path / "data"
    (data / "t" / "imports" / "custom").mkdir(parents=True)
    (data / "prices" / "AAPL").mkdir(parents=True)
    (data / "prices" / "USDPLN").mkdir(parents=True)

    today = date.today()
    yr = today.year
    # Price slabs for the last 3 years (weekly-ish dates are enough for the chart)
    aapl = {f"{y}-{m:02d}-{d:02d}": 200.0 + m for y in (yr - 2, yr - 1, yr)
            for m in range(1, 13) for d in (5, 12, 19, 26)}
    usdpln = {f"{y}-{m:02d}-{d:02d}": 3.9 for y in (yr - 2, yr - 1, yr)
              for m in range(1, 13) for d in (5, 12, 19, 26)}
    for y in (yr - 2, yr - 1, yr):
        (data / "prices" / "AAPL" / f"{y}.json").write_text(
            json.dumps({k: v for k, v in aapl.items() if k.startswith(str(y))}))
        (data / "prices" / "USDPLN" / f"{y}.json").write_text(
            json.dumps({k: v for k, v in usdpln.items() if k.startswith(str(y))}))

    (data / "config.json").write_text(json.dumps({"default_currency": "PLN", "theme": "dark"}))
    (data / "projects.json").write_text(
        json.dumps({"t": {"created_at": "2026-01-01T00:00:00", "last_refresh": "2026-09-01"}}))

    txs = [
        {"date": f"{yr - 2}-03-15", "entries": [{"ticker": "AAPL", "amount": 10.0}, {"ticker": "USD", "amount": -2000.0}]},
        {"date": f"{yr - 1}-04-15", "entries": [{"ticker": "AAPL", "amount": 8.0}, {"ticker": "USD", "amount": -1600.0}]},
        {"date": f"{yr}-02-15", "entries": [{"ticker": "AAPL", "amount": 7.0}, {"ticker": "USD", "amount": -1400.0}]},
    ]
    with (data / "t" / "transactions.jsonl").open("w") as f:
        for r in txs:
            f.write(json.dumps(r) + "\n")

    # A broker file so "Refresh data" actually re-imports something
    (data / "t" / "imports" / "custom" / "regression.json").write_text(json.dumps([
        {"date": f"{yr}-06-01", "entries": [{"ticker": "AAPL", "amount": 3.0}, {"ticker": "USD", "amount": -600.0}]},
    ]))

    wrapper = tmp_path / "app_wrapper.py"
    wrapper.write_text(WRAPPER_APP.format(repo=str(REPO), tmp=str(tmp_path)))
    return wrapper
def test_range_survives_refresh_and_all_charts_respect_range(tmp_path: Path):
    from streamlit.testing.v1 import AppTest

    wrapper = _build_temp_app(tmp_path)
    at = AppTest.from_file(str(wrapper), default_timeout=120)
    at.run()
    assert not at.exception, f"app crashed on first run: {[e.message for e in at.exception]}"

    # 1. Select "Last 3 months"
    sel = next(w for w in at.sidebar.selectbox if w.label == "Range")
    sel.set_value("Last 3 months")
    at.run()
    assert not at.exception

    today = date.today()
    expect_start = today - timedelta(days=90)

    # 2. Refresh data (re-imports the broker file)
    btn = next(b for b in at.sidebar.button if "Refresh data" in (b.label or ""))
    btn.click()
    at.run()

    # 3. Range state must survive the refresh
    assert not at.exception, f"app crashed on refresh: {[e.message for e in at.exception]}"
    assert at.session_state["_range"] == "Last 3 months"
    assert at.session_state["chart_start"] == expect_start
    assert at.session_state["chart_end"] == today

    # 4. EVERY rendered time-series chart must span only the selected range.
    #    Regression guard: the drawdown chart used to receive the unfiltered
    #    all_snapshots and always showed the full history.
    expect_start_iso = expect_start.isoformat()
    end_iso = today.isoformat()
    checked = 0
    for el in at.get("plotly_chart"):
        spec_raw = el.proto.spec
        spec = json.loads(spec_raw if isinstance(spec_raw, str) else spec_raw.decode())
        for tr in spec.get("data", []):
            xs = tr.get("x") or []
            if not xs or tr.get("type") != "scatter":
                continue
            first, last = str(xs[0]), str(xs[-1])
            assert first >= expect_start_iso, (
                f"chart trace spans full history ({first} < {expect_start_iso}) "
                "— range filter regressed"
            )
            assert last <= end_iso
            checked += 1
    # Main portfolio chart (2 traces) + drawdown (1 trace) must have been checked
    assert checked >= 3, f"expected >=3 filtered traces, got {checked}"


def test_no_duplicate_plotly_element_ids(tmp_path: Path):
    """Allocation donuts + drawdown must not collide on auto-generated IDs.

    Regression guard for StreamlitDuplicateElementId: two bare
    st.plotly_chart(fig, width='stretch') calls crashed the whole dashboard
    as soon as >=2 allocation categories rendered.
    """
    from streamlit.testing.v1 import AppTest

    wrapper = _build_temp_app(tmp_path)
    at = AppTest.from_file(str(wrapper), default_timeout=120)
    at.run()
    assert not at.exception, (
        f"duplicate plotly element IDs (or other crash): {[e.message for e in at.exception]}"
    )
    # Main chart + 4 allocation donuts + drawdown = 6 plotly charts minimum
    n_charts = len(at.get("plotly_chart"))
    assert n_charts >= 6, f"expected >=6 plotly charts, got {n_charts}"