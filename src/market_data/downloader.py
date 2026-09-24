"""
downloader.py — isolated Yahoo Finance price and FX downloader with output suppression and retry mechanisms.
"""
from __future__ import annotations

import atexit
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Callable

import pandas as pd
import yfinance as yf

from domain.currencies import CURRENCY_SUFFIXES, SUPPORTED_CURRENCIES, TRIANGULATE_VIA_USD
from domain.exceptions import PriceFetchError
from storage import has_price_year, load_ticker_names, save_price_year

log = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

_DEVNULL_STREAM = open(os.devnull, "w", encoding="utf-8")
atexit.register(_DEVNULL_STREAM.close)

_devnull_fd = os.open(os.devnull, os.O_WRONLY)
_suppress_lock = threading.Lock()
_suppress_count = 0
_suppress_saved_stdout: int = -1
_suppress_saved_stderr: int = -1


@contextmanager
def suppress_output():
    """Suppress stdout/stderr to silence yfinance download noise."""
    global _suppress_count, _suppress_saved_stdout, _suppress_saved_stderr
    with _suppress_lock:
        _suppress_count += 1
        if _suppress_count == 1:
            _suppress_saved_stdout = os.dup(sys.stdout.fileno())
            _suppress_saved_stderr = os.dup(sys.stderr.fileno())
            os.dup2(_devnull_fd, sys.stdout.fileno())
            os.dup2(_devnull_fd, sys.stderr.fileno())
    try:
        yield
    finally:
        with _suppress_lock:
            _suppress_count -= 1
            if _suppress_count == 0:
                os.dup2(_suppress_saved_stdout, sys.stdout.fileno())
                os.dup2(_suppress_saved_stderr, sys.stderr.fileno())
                os.close(_suppress_saved_stdout)
                os.close(_suppress_saved_stderr)


FX_YAHOO: dict[str, str] = {
    f"{ccy}PLN": f"{ccy}PLN=X"
    for ccy in CURRENCY_SUFFIXES if ccy not in ("PLN", *TRIANGULATE_VIA_USD)
}
FX_YAHOO["USDPLN"] = "USDPLN=X"
FX_YAHOO["EURUSD"] = "EURUSD=X"
for ccy in TRIANGULATE_VIA_USD:
    FX_YAHOO[f"{ccy}USD"] = f"{ccy}USD=X"

_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 0.5


def yahoo_symbol(ticker: str) -> str:
    """Map internal ticker name to Yahoo Finance symbol."""
    return FX_YAHOO.get(ticker, ticker)


def download_year(ticker: str, year: int) -> dict[str, float] | None:
    """Download full-year close prices for ticker from Yahoo Finance."""
    today = date.today()
    start = date(year, 1, 1)
    end = min(date(year, 12, 31), today)

    if start > today:
        return None

    symbol = yahoo_symbol(ticker)

    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with suppress_output():
                df = yf.download(
                    symbol,
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    progress=False,
                    auto_adjust=False,
                )
            if df is not None and not df.empty and "Close" in df.columns:
                close = df["Close"]
                if hasattr(close, "columns"):
                    close = close.iloc[:, 0]
                close = close.dropna()
                if ticker.endswith(".L") and not close.empty:
                    try:
                        if yf.Ticker(symbol).fast_info.currency == "GBp":
                            close = close / 100.0
                    except Exception:
                        pass
                return {
                    d.strftime("%Y-%m-%d"): round(float(v), 4)
                    for d, v in close.items()
                }
            if df is not None and df.empty:
                return {}
        except Exception as e:
            if attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY)
            else:
                log.warning("download failed for %s (%d): %s", ticker, year, e)
    return None


def ensure_batch(
    tickers: list[str],
    start_date: date,
    end_date: date | None = None,
    force_refresh_current_year: bool = True,
    progress_cb: Callable[[str], None] | None = None,
    adjusted: bool = False,
) -> list[str]:
    """Populate price caches for many tickers with a single batched Yahoo download."""
    today = date.today()
    if end_date is None:
        end_date = today
    end = min(end_date, today)

    def _notify(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    symbols = [t for t in dict.fromkeys(tickers) if t.upper() not in SUPPORTED_CURRENCIES]
    if not symbols:
        return []

    needed_years: dict[str, set[int]] = {}
    for t in symbols:
        yrs = {
            y for y in range(start_date.year, end.year + 1)
            if (y == today.year and force_refresh_current_year)
            or not has_price_year(t, y, adjusted=adjusted)
        }
        if yrs:
            needed_years[t] = yrs

    failed: list[str] = sorted(t for t, yrs in needed_years.items() if not yrs)
    if not needed_years:
        return failed

    batch_start = date(min(min(yrs) for yrs in needed_years.values()), 1, 1)
    pair_by_sym = {yahoo_symbol(t): t for t in needed_years}
    sym_list = list(pair_by_sym.keys())

    kind = "adjusted benchmark" if adjusted else "tickers"
    _notify(f"Downloading {len(sym_list)} {kind} ({batch_start.year}–{end.year})…")

    df = None
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with suppress_output():
                df = yf.download(
                    sym_list,
                    start=batch_start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    progress=False,
                    auto_adjust=adjusted,
                    group_by="ticker",
                    threads=True,
                )
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY)

    if df is None or df.empty:
        if last_exc is not None:
            log.warning("batch download failed: %s", last_exc)
        return sorted(needed_years.keys())

    closes: dict[str, object] = {}
    field_names = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
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
                if sym in lvl0 and "Close" in df[sym].columns:
                    closes[sym] = df[sym]["Close"]
    elif "Close" in df.columns and sym_list:
        closes[sym_list[0]] = df["Close"]

    gbp_cache: dict[str, bool] = {}
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

        saved_any = False
        for y in needed_years[ticker]:
            sub = series[series.index.year == y]
            if not sub.empty:
                year_data = {
                    d.strftime("%Y-%m-%d"): round(float(v), 4)
                    for d, v in sub.items()
                }
                save_price_year(ticker, y, year_data, adjusted=adjusted)
                saved_any = True
            elif y < today.year and not has_price_year(ticker, y, adjusted=adjusted):
                save_price_year(ticker, y, {}, adjusted=adjusted)
        if not saved_any and not series.empty:
            failed.append(ticker)
        elif series.empty and not any(has_price_year(ticker, y, adjusted=adjusted) for y in needed_years[ticker]):
            failed.append(ticker)

    return sorted(dict.fromkeys(failed))
