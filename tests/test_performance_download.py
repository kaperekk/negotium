"""
Performance tests for Yahoo Finance download pipeline.

Measures real-world download performance for 20 popular worldwide stocks
across different regions (US, Europe, Poland, Asia).

Run with:
    pytest tests/test_performance_download.py -v -s
    pytest tests/test_performance_download.py -v -s -m slow

Standalone:
    python tests/run_perf_download.py
"""
from __future__ import annotations

import importlib
import sys
import time
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path

import pytest

# Ensure src/ is importable
SRC = Path(__file__).resolve().parent.parent / "src"
ROOT = Path(__file__).resolve().parent.parent
for _p in (str(SRC), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 20 popular worldwide tickers across regions
PERF_TICKERS = [
    # US (5)
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    # Europe (5)
    "SAP.DE", "ASML.AS", "NOV.DE", "ERIC-B.ST", "SXR8.DE",
    # Poland (5)
    "CBF.WA", "SHO.WA", "XTB.WA", "KRU.WA", "SNT.WA",
    # Asia (5)
    "9988.HK", "0700.HK", "6758.T", "005930.KS", "9984.T",
]


def _format_duration(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f}us"
    if seconds < 1.0:
        return f"{seconds * 1000:.1f}ms"
    return f"{seconds:.3f}s"


def _print_timing_table(title: str, timings: list[dict]) -> None:
    """Print a formatted timing breakdown table."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")

    header = f"{'Ticker':<12} {'Name Res':>10} {'Download':>10} {'Parse+Write':>12} {'Total':>10} {'Rows':>8}"
    print(header)
    print("-" * 80)

    totals = {"name_res": 0.0, "download": 0.0, "parse_write": 0.0, "total": 0.0}
    total_rows = 0

    for t in timings:
        name_res = _format_duration(t["name_res"])
        download = _format_duration(t["download"])
        parse_write = _format_duration(t["parse_write"])
        total = _format_duration(t["total"])
        rows = str(t.get("rows", "?"))
        print(f"{t['ticker']:<12} {name_res:>10} {download:>10} {parse_write:>12} {total:>10} {rows:>8}")

        totals["name_res"] += t["name_res"]
        totals["download"] += t["download"]
        totals["parse_write"] += t["parse_write"]
        totals["total"] += t["total"]
        total_rows += t.get("rows", 0)

    print("-" * 80)
    print(
        f"{'TOTAL':<12} "
        f"{_format_duration(totals['name_res']):>10} "
        f"{_format_duration(totals['download']):>10} "
        f"{_format_duration(totals['parse_write']):>12} "
        f"{_format_duration(totals['total']):>10} "
        f"{total_rows:>8}"
    )

    if totals["total"] > 0:
        pct_name = totals["name_res"] / totals["total"] * 100
        pct_dl = totals["download"] / totals["total"] * 100
        pct_pw = totals["parse_write"] / totals["total"] * 100
        print(
            f"{'  %':<12} "
            f"{pct_name:>9.1f}% "
            f"{pct_dl:>9.1f}% "
            f"{pct_pw:>11.1f}% "
        )

    print(f"\n  Bottleneck: ", end="")
    phases = [
        ("Name Resolution", totals["name_res"]),
        ("Yahoo Download", totals["download"]),
        ("Parse + Cache Write", totals["parse_write"]),
    ]
    bottleneck = max(phases, key=lambda x: x[1])
    print(f"{bottleneck[0]} ({_format_duration(bottleneck[1])}, "
          f"{bottleneck[1] / totals['total'] * 100:.1f}% of total)")
    print(f"{'=' * 80}\n")


def _run_download_perf(
    tickers: list[str],
    start_date: date,
    end_date: date,
    tmp: Path,
) -> list[dict]:
    """Run download performance measurement, returning per-ticker timing dicts."""
    import storage
    import ticker_data
    import config as cfg_module

    # Patch storage roots to temp dir
    storage.ROOT = tmp
    storage.DATA_ROOT = tmp / "data"
    storage.PRICES_DIR = tmp / "data" / "prices"
    storage.ADJ_PRICES_DIR = tmp / "data" / "prices_adj"
    storage.PROJECTS_PATH = tmp / "data" / "projects.json"

    storage.set_current_project("perf_test")

    cfg_module.ROOT = tmp
    cfg_module.GLOBAL_CONFIG_PATH = tmp / "data" / "config.json"

    results = []

    for ticker in tickers:
        timing = {"ticker": ticker, "name_res": 0.0, "download": 0.0, "parse_write": 0.0, "total": 0.0, "rows": 0}
        t_total_start = time.perf_counter()

        # Phase 1: Name resolution
        t0 = time.perf_counter()
        name = ticker_data.get_ticker_name(ticker)
        timing["name_res"] = time.perf_counter() - t0

        # Phase 2+3: Download + parse + cache write via ensure()
        t0 = time.perf_counter()
        ticker_data.ensure(
            ticker,
            start_date,
            end_date,
            force_refresh_current_year=True,
        )
        timing["download"] = time.perf_counter() - t0

        # Count rows (trading days) cached
        total_rows = 0
        for year in range(start_date.year, end_date.year + 1):
            prices = storage.load_price_year(ticker, year)
            total_rows += len(prices)
        timing["rows"] = total_rows

        timing["total"] = time.perf_counter() - t_total_start
        results.append(timing)

    return results


def _run_parallel_download_perf(
    tickers: list[str],
    start_date: date,
    end_date: date,
    tmp: Path,
) -> list[dict]:
    """Run ensure_parallel() performance measurement."""
    import storage
    import ticker_data
    import config as cfg_module

    storage.ROOT = tmp
    storage.DATA_ROOT = tmp / "data"
    storage.PRICES_DIR = tmp / "data" / "prices"
    storage.ADJ_PRICES_DIR = tmp / "data" / "prices_adj"
    storage.PROJECTS_PATH = tmp / "data" / "projects.json"

    storage.set_current_project("perf_test")

    cfg_module.ROOT = tmp
    cfg_module.GLOBAL_CONFIG_PATH = tmp / "data" / "config.json"

    t_start = time.perf_counter()
    failed = ticker_data.ensure_parallel(
        tickers,
        start_date,
        end_date,
        force_refresh_current_year=True,
        max_workers=5,
    )
    total_elapsed = time.perf_counter() - t_start

    # Count rows per ticker
    results = []
    for ticker in tickers:
        total_rows = 0
        for year in range(start_date.year, end_date.year + 1):
            prices = storage.load_price_year(ticker, year)
            total_rows += len(prices)
        # Evenly split total time across tickers (they ran concurrently)
        results.append({
            "ticker": ticker,
            "name_res": 0.0,
            "download": total_elapsed / len(tickers),
            "parse_write": 0.0,
            "total": total_elapsed / len(tickers),
            "rows": total_rows,
        })

    return results


def _run_batch_download_perf(
    tickers: list[str],
    start_date: date,
    end_date: date,
    tmp: Path,
) -> list[dict]:
    """Run batch download performance measurement with detailed phase timing.

    This instruments the batch path by monkeypatching yf.download to capture
    the network phase separately from parsing/caching.
    """
    import pandas as pd
    import storage
    import ticker_data
    import config as cfg_module
    import yfinance as yf

    # Patch storage roots to temp dir
    storage.ROOT = tmp
    storage.DATA_ROOT = tmp / "data"
    storage.PRICES_DIR = tmp / "data" / "prices"
    storage.ADJ_PRICES_DIR = tmp / "data" / "prices_adj"
    storage.PROJECTS_PATH = tmp / "data" / "projects.json"

    storage.set_current_project("perf_test")

    cfg_module.ROOT = tmp
    cfg_module.GLOBAL_CONFIG_PATH = tmp / "data" / "config.json"

    today = date.today()
    end = min(end_date, today)

    # Phase 1: Name resolution (all tickers)
    t_name_start = time.perf_counter()
    for t in tickers:
        ticker_data.get_ticker_name(t)
    name_elapsed = time.perf_counter() - t_name_start

    # Filter out cash tickers
    symbols = [t for t in dict.fromkeys(tickers) if t.upper() not in storage.SUPPORTED_CURRENCIES]
    if not symbols:
        return []

    # Compute needed years
    needed_years = {}
    for t in symbols:
        yrs = {
            y for y in range(start_date.year, end.year + 1)
            if (y == today.year) or not storage.has_price_year(t, y)
        }
        if yrs:
            needed_years[t] = yrs

    if not needed_years:
        return [{"ticker": t, "name_res": 0.0, "download": 0.0, "parse_write": 0.0, "total": 0.0, "rows": 0} for t in tickers]

    batch_start = date(min(min(yrs) for yrs in needed_years.values()), 1, 1)
    pair_by_sym = {ticker_data._yahoo_symbol(t): t for t in needed_years}
    sym_list = list(pair_by_sym.keys())

    # Phase 2: Batch Yahoo download
    df = None
    t_download_start = time.perf_counter()
    try:
        with ticker_data._suppress_output():
            df = yf.download(
                sym_list,
                start=batch_start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                progress=False,
                auto_adjust=False,
                group_by="ticker",
                threads=True,
            )
    except Exception as e:
        print(f"  Batch download failed: {e}")
        df = None
    download_elapsed = time.perf_counter() - t_download_start

    # Phase 3: Parse DataFrame + write cache
    t_parse_start = time.perf_counter()
    closes = {}
    field_names = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
    if df is not None and not df.empty:
        if isinstance(df.columns, pd.MultiIndex):
            lvl0 = list(dict.fromkeys(df.columns.get_level_values(0)))
            if set(lvl0) <= field_names:
                if "Close" in lvl0:
                    sub = df["Close"]
                    for sym in sym_list:
                        if sym in sub.columns:
                            closes[sym] = sub[sym]
            else:
                for sym in sym_list:
                    if lvl0 and sym in lvl0 and "Close" in df[sym].columns:
                        closes[sym] = df[sym]["Close"]
        elif "Close" in df.columns and sym_list:
            closes[sym_list[0]] = df["Close"]

    gbp_cache = {}
    rows_per_ticker = {}
    for sym, ticker in pair_by_sym.items():
        series = closes.get(sym)
        series = (series if series is not None else pd.Series(dtype=float)).dropna()

        if ticker.endswith(".L") and not series.empty:
            is_gbp = gbp_cache.get(sym)
            if is_gbp is None:
                try:
                    cur = yf.Ticker(sym).fast_info.currency
                except Exception:
                    cur = None
                is_gbp = (cur == "GBp")
                gbp_cache[sym] = is_gbp
            if is_gbp:
                series = series / 100.0

        total_rows = 0
        for year in sorted(needed_years[ticker]):
            yr_series = series[series.index.year == year]
            prices = {str(ts.date()): round(float(v), 6) for ts, v in yr_series.items()}
            if prices:
                storage.save_price_year(ticker, year, prices)
            total_rows += len(prices)
        rows_per_ticker[ticker] = total_rows

    parse_elapsed = time.perf_counter() - t_parse_start
    total_elapsed = time.perf_counter() - t_name_start

    # Build per-ticker results (batch download time is shared, so we split
    # proportionally by row count; name resolution and parse are per-ticker)
    total_rows_all = sum(rows_per_ticker.values()) or 1
    results = []
    for ticker in tickers:
        rows = rows_per_ticker.get(ticker, 0)
        # Proportional share of the batch download time
        dl_share = download_elapsed * (rows / total_rows_all) if rows else 0
        # Name resolution was measured per-ticker above (we used the sum)
        # Approximate per-ticker name cost
        name_share = name_elapsed / len(tickers)
        # Parse share proportional to rows
        parse_share = parse_elapsed * (rows / total_rows_all) if rows else 0
        total_share = name_share + dl_share + parse_share

        results.append({
            "ticker": ticker,
            "name_res": name_share,
            "download": dl_share,
            "parse_write": parse_share,
            "total": total_share,
            "rows": rows,
        })

    return results


@pytest.mark.slow
def test_perf_download_full_history(tmp_path: Path):
    """Download 20 stocks for 2023-2026 (full history, like refresh market data).

    Measures per-ticker time broken into: name resolution, download, parse+write.
    Prints a timing table showing where time is spent.
    """
    today = date.today()
    start_date = date(2023, 1, 1)
    end_date = today

    print(f"\n{'#' * 80}")
    print(f"  PERFORMANCE TEST: Full History Download ({start_date.year}-{end_date.year})")
    print(f"  {len(PERF_TICKERS)} tickers | {start_date} to {end_date}")
    print(f"{'#' * 80}")

    # Test 1: Individual ensure() calls (serial, per-ticker with parallel years)
    print("\n--- Serial download (one ticker at a time, parallel years) ---")
    timings_serial = _run_download_perf(PERF_TICKERS, start_date, end_date, tmp_path)
    _print_timing_table(
        f"Serial Download ({start_date.year}-{end_date.year})",
        timings_serial,
    )

    # Test 2: ensure_parallel() — all tickers in parallel
    print("\n--- Parallel ensure (all tickers concurrently) ---")
    timings_parallel = _run_parallel_download_perf(PERF_TICKERS, start_date, end_date, tmp_path)
    _print_timing_table(
        f"Parallel Ensure ({start_date.year}-{end_date.year})",
        timings_parallel,
    )

    # Test 3: Batch ensure_batch() call (single yf.download call)
    print("\n--- Batch download (all tickers in one yf.download call) ---")
    timings_batch = _run_batch_download_perf(PERF_TICKERS, start_date, end_date, tmp_path)
    _print_timing_table(
        f"Batch Download ({start_date.year}-{end_date.year})",
        timings_batch,
    )

    # Summary comparison
    serial_total = sum(t["total"] for t in timings_serial)
    parallel_total = sum(t["total"] for t in timings_parallel)
    batch_total = sum(t["total"] for t in timings_batch) if timings_batch else 0
    print(f"\n--- Summary ---")
    print(f"  Serial total:     {_format_duration(serial_total)}")
    print(f"  Parallel total:   {_format_duration(parallel_total)}")
    print(f"  Batch total:      {_format_duration(batch_total)}")
    if serial_total > 0 and parallel_total > 0:
        print(f"  Serial→Parallel:  {serial_total / parallel_total:.1f}x faster")
    if serial_total > 0 and batch_total > 0:
        print(f"  Serial→Batch:     {serial_total / batch_total:.1f}x faster")

    # Assertions: tests pass if downloads complete without error
    assert len(timings_serial) == len(PERF_TICKERS), "Not all tickers were processed"
    for t in timings_serial:
        assert t["total"] > 0, f"{t['ticker']} had zero elapsed time"
        assert t["rows"] > 0, f"{t['ticker']} downloaded zero rows"


@pytest.mark.slow
def test_perf_download_single_day(tmp_path: Path):
    """Download 20 stocks for just the current year (simulates daily refresh).

    Measures per-ticker time to see overhead of a single-day vs full history.
    """
    today = date.today()
    start_date = date(today.year, 1, 1)
    end_date = today

    print(f"\n{'#' * 80}")
    print(f"  PERFORMANCE TEST: Single Day Download ({today})")
    print(f"  {len(PERF_TICKERS)} tickers | current year only")
    print(f"{'#' * 80}")

    # Serial download (current year only)
    print("\n--- Serial download (current year only) ---")
    timings_serial = _run_download_perf(PERF_TICKERS, start_date, end_date, tmp_path)
    _print_timing_table(
        f"Serial Download ({today.year} only)",
        timings_serial,
    )

    # Parallel ensure (current year only)
    print("\n--- Parallel ensure (current year only) ---")
    timings_parallel = _run_parallel_download_perf(PERF_TICKERS, start_date, end_date, tmp_path)
    _print_timing_table(
        f"Parallel Ensure ({today.year} only)",
        timings_parallel,
    )

    # Batch download (current year only)
    print("\n--- Batch download (current year only) ---")
    timings_batch = _run_batch_download_perf(PERF_TICKERS, start_date, end_date, tmp_path)
    _print_timing_table(
        f"Batch Download ({today.year} only)",
        timings_batch,
    )

    serial_total = sum(t["total"] for t in timings_serial)
    parallel_total = sum(t["total"] for t in timings_parallel)
    batch_total = sum(t["total"] for t in timings_batch) if timings_batch else 0
    print(f"\n--- Summary ---")
    print(f"  Serial total:     {_format_duration(serial_total)}")
    print(f"  Parallel total:   {_format_duration(parallel_total)}")
    print(f"  Batch total:      {_format_duration(batch_total)}")
    if serial_total > 0 and parallel_total > 0:
        print(f"  Serial→Parallel:  {serial_total / parallel_total:.1f}x faster")
    if serial_total > 0 and batch_total > 0:
        print(f"  Serial→Batch:     {serial_total / batch_total:.1f}x faster")

    assert len(timings_serial) == len(PERF_TICKERS), "Not all tickers were processed"
    for t in timings_serial:
        assert t["total"] > 0, f"{t['ticker']} had zero elapsed time"


if __name__ == "__main__":
    # Allow running directly: python tests/test_performance_download.py
    import tempfile
    with tempfile.TemporaryDirectory(prefix="perf_test_") as tmp:
        tmp_path = Path(tmp)
        print("Running full history performance test...")
        test_perf_download_full_history(tmp_path)
        print("\n\nRunning single day performance test...")
        # Fresh tmp for second test
        tmp_path2 = Path(tempfile.mkdtemp(prefix="perf_test_day_"))
        test_perf_download_single_day(tmp_path2)
