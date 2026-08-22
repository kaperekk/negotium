"""
ticker_data.py — download and cache price data from Yahoo Finance

Cache layout: data/{TICKER}/{YEAR}.json  → {YYYY-MM-DD: close_price}

FX tickers (used to convert currencies to PLN):
  USD → PLN:  USDPLN=X
  EUR → PLN:  EURPLN=X
  EUR → USD:  EURUSD=X

A currency ticker (USD, EUR, PLN) is treated as cash — 1 unit = 1 in that CCY.
The FX pairs are fetched like any other ticker so that portfolio values can all
be expressed in the user's chosen base currency.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import date, timedelta
from typing import Callable

import yfinance as yf

log = logging.getLogger(__name__)
logging.getLogger("yfinance").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)


@contextmanager
def _suppress_output():
    """Suppress stdout/stderr to silence yfinance download noise (thread-safe)."""
    with open(os.devnull, "w") as devnull:
        with redirect_stdout(devnull), redirect_stderr(devnull):
            yield

from storage import (
    has_price_year,
    load_price_year,
    save_price_year,
    load_ticker_names,
    save_ticker_names,
    SUPPORTED_CURRENCIES,
    CURRENCY_SUFFIXES,
    TRIANGULATE_VIA_USD,
)

# Yahoo symbols for FX cross rates (all → PLN)
FX_YAHOO: dict[str, str] = {
    f"{ccy}PLN": f"{ccy}PLN=X"
    for ccy in CURRENCY_SUFFIXES if ccy not in ("PLN", *TRIANGULATE_VIA_USD)
}
FX_YAHOO["EURUSD"] = "EURUSD=X"
for ccy in TRIANGULATE_VIA_USD:
    FX_YAHOO[f"{ccy}USD"] = f"{ccy}USD=X"

_RETRY_ATTEMPTS = 3
_RETRY_DELAY    = 2   # seconds


def _yahoo_symbol(ticker: str) -> str:
    """Map internal ticker name to Yahoo Finance symbol."""
    return FX_YAHOO.get(ticker, ticker)


def get_ticker_name(ticker: str) -> str:
    """Return company short name for a ticker, cached to disk. Falls back to ticker."""
    if ticker.upper() in SUPPORTED_CURRENCIES:
        return ticker
    names = load_ticker_names()
    if ticker in names:
        return names[ticker]
    try:
        with _suppress_output():
            info = yf.Ticker(_yahoo_symbol(ticker)).info
        short = info.get("shortName") or info.get("longName") or ticker
    except Exception:
        short = ticker
    names[ticker] = short
    save_ticker_names(names)
    return short


def _download_year(ticker: str, year: int) -> dict[str, float]:
    """
    Download full-year close prices for ticker from Yahoo Finance.
    Returns {YYYY-MM-DD: close} — may be empty for future years or bad tickers.
    """
    today = date.today()
    start = date(year, 1, 1)
    # Don't ask for dates beyond today
    end   = min(date(year, 12, 31), today)

    if start > today:
        return {}

    symbol = _yahoo_symbol(ticker)

    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with _suppress_output():
                df = yf.download(
                    symbol,
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    progress=False,
                    auto_adjust=True,
                )
            if df.empty:
                return {}

            # Handle MultiIndex columns (yfinance >= 0.2.x)
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(0)

            close = df["Close"].dropna()

            # Convert GBp (pence) to GBP — Yahoo returns pence for LSE tickers
            try:
                cur = yf.Ticker(symbol).fast_info.currency
                if cur == "GBp":
                    close = close / 100.0
            except Exception:
                pass

            return {str(d.date()): round(float(v), 6) for d, v in close.items()}

        except Exception as exc:
            if attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY)
            else:
                log.warning("could not download %s %s: %s", symbol, year, exc)
                return {}

    return {}


def ensure(
    ticker: str,
    start_date: date,
    end_date: date | None = None,
    force_refresh_current_year: bool = True,
    progress_cb: Callable[[str], None] | None = None,
) -> None:
    """
    Ensure price cache is populated for ticker from start_date to end_date.

    - Historical years (fully elapsed): downloaded once, never re-fetched.
    - Current year: always re-fetched so we get the latest closes.
    - Cash tickers (USD/EUR/PLN): skipped — no price data needed.
    Also fetches and caches the ticker's company name.
    """
    if ticker.upper() in SUPPORTED_CURRENCIES:
        return  # cash holds its own value

    # Ensure name is cached
    names = load_ticker_names()
    if ticker not in names:
        get_ticker_name(ticker)

    if end_date is None:
        end_date = date.today()

    start_year = start_date.year
    end_year   = end_date.year
    today_year = date.today().year

    for year in range(start_year, end_year + 1):
        is_current = (year == today_year)
        already_cached = has_price_year(ticker, year)

        if already_cached and not (is_current and force_refresh_current_year):
            continue

        if progress_cb:
            progress_cb(f"Downloading {ticker} {year}…")

        prices = _download_year(ticker, year)
        if prices:
            save_price_year(ticker, year, prices)


def ensure_batch(
    tickers: list[str],
    start_date: date,
    end_date: date | None = None,
    force_refresh_current_year: bool = True,
    progress_cb: Callable[[str], None] | None = None,
) -> list[str]:
    """
    Populate price caches for many tickers with a single batched Yahoo download.

    Same cache rules as ensure(): historical years already on disk are kept,
    the current year is re-fetched so latest closes are picked up.

    Returns tickers for which no data could be retrieved.
    """
    import pandas as pd

    today = date.today()
    if end_date is None:
        end_date = today
    end = min(end_date, today)

    def _notify(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    symbols = [t for t in dict.fromkeys(tickers)
               if t.upper() not in SUPPORTED_CURRENCIES]
    if not symbols:
        return []

    names = load_ticker_names()
    for t in symbols:
        if t not in names:
            get_ticker_name(t)

    needed_years: dict[str, set[int]] = {}
    for t in symbols:
        yrs = {
            y for y in range(start_date.year, end.year + 1)
            if (y == today.year and force_refresh_current_year)
            or not has_price_year(t, y)
        }
        if yrs:
            needed_years[t] = yrs

    failed: list[str] = sorted(t for t, yrs in needed_years.items() if not yrs)
    if not needed_years:
        return failed

    batch_start = date(min(min(yrs) for yrs in needed_years.values()), 1, 1)
    pair_by_sym = {_yahoo_symbol(t): t for t in needed_years}
    sym_list = list(pair_by_sym.keys())

    _notify(f"Downloading {len(sym_list)} tickers ({batch_start.year}–{end.year})…")

    df = None
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with _suppress_output():
                df = yf.download(
                    sym_list,
                    start=batch_start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    progress=False,
                    auto_adjust=True,
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

    # Normalize to {yahoo_symbol: Close series} across yfinance column layouts
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
    total = len(needed_years)
    for i, (sym, ticker) in enumerate(pair_by_sym.items(), start=1):
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
        for year in sorted(needed_years[ticker]):
            yr_series = series[series.index.year == year]
            prices = {str(ts.date()): round(float(v), 6) for ts, v in yr_series.items()}
            if prices:
                save_price_year(ticker, year, prices)
                saved_any = True
        if not saved_any and ticker not in failed:
            failed.append(ticker)
        _notify(f"✓ {ticker} ({i}/{total})")

    # Yahoo sometimes silently drops symbols from large batch requests —
    # retry stragglers one-by-one with the single-ticker path.
    for ticker in list(failed):
        try:
            ensure(ticker, start_date, end_date, force_refresh_current_year)
            if any(has_price_year(ticker, y)
                   for y in needed_years.get(ticker, set())):
                failed.remove(ticker)
        except Exception as exc:
            log.warning("single-ticker fallback failed for %s: %s", ticker, exc)

    return sorted(failed)


def get_price(
    ticker: str,
    on_date: str,
    cache: dict[str, dict[str, float]],
    year: int,
) -> float | None:
    """
    Return close price for ticker on on_date (YYYY-MM-DD).

    `cache` is a dict[ticker][year] → {date_str: price} — mutated in place
    for performance so callers can reuse it across many calls.

    If the exact date is missing (weekend/holiday), walks back up to 5 days.
    Returns None if no price found.
    """
    if ticker.upper() in SUPPORTED_CURRENCIES:
        return 1.0  # cash is always worth 1 in its own currency

    # Populate cache entry if missing
    if ticker not in cache:
        cache[ticker] = {}
    if year not in cache[ticker]:
        cache[ticker][year] = load_price_year(ticker, year)

    year_prices = cache[ticker][year]

    # Walk back up to 5 calendar days (covers weekends + holidays)
    check = date.fromisoformat(on_date)
    for _ in range(7):
        s = check.isoformat()
        if s in year_prices:
            return year_prices[s]
        check -= timedelta(days=1)
        # If we crossed a year boundary, load the previous year too
        if check.year != year:
            prev = check.year
            if prev not in cache[ticker]:
                cache[ticker][prev] = load_price_year(ticker, prev)
            year_prices = cache[ticker][prev]
            year = prev

    return None


def _latest_price(
    ticker: str,
    cache: dict,
    year: int,
) -> float | None:
    """
    Return the most recent cached price for ticker, scanning loaded slabs.

    Used as a fallback when the priced date is missing (stale cache), so FX
    conversions do not silently collapse to 1.0. Returns None if unavailable.
    """
    if ticker.upper() in SUPPORTED_CURRENCIES:
        return 1.0
    if ticker not in cache or not isinstance(cache[ticker], dict):
        if ticker not in cache:
            return None
    for y in sorted(cache[ticker].keys(), reverse=True):
        slab = cache[ticker].get(y) or {}
        if not slab:
            continue
        return slab[max(slab.keys())]
    return None


def get_fx_rate(
    from_ccy: str,
    to_ccy: str,
    on_date: str,
    cache: dict,
    year: int,
) -> float:
    """
    Return exchange rate from_ccy → to_ccy on on_date.

    Looks up the exact date first, then falls back to the most recent cached
    rate for the same conversion so stale data does not produce a bogus 1.0.
    Falls back to 1.0 only if no rate is available at all.
    """
    if from_ccy == to_ccy:
        return 1.0

    pair    = f"{from_ccy}{to_ccy}"
    reverse = f"{to_ccy}{from_ccy}"

    def _rate(ticker: str) -> float | None:
        v = get_price(ticker, on_date, cache, year)
        if v is not None:
            return v
        return _latest_price(ticker, cache, year)

    # Try direct pair
    if pair in FX_YAHOO:
        rate = _rate(pair)
        if rate is not None:
            return rate

    # Try reverse pair
    if reverse in FX_YAHOO:
        rate = _rate(reverse)
        if rate is not None and rate != 0:
            return 1.0 / rate

    # Triangulate via USD for currencies without direct pair
    usd_pln = _rate("USDPLN")
    eur_usd = _rate("EURUSD")

    if from_ccy == "EUR" and to_ccy == "PLN" and eur_usd and usd_pln:
        return eur_usd * usd_pln
    if from_ccy == "PLN" and to_ccy == "EUR" and eur_usd and usd_pln:
        return 1.0 / (eur_usd * usd_pln)
    if from_ccy == "GBP" and to_ccy == "PLN" and usd_pln:
        return usd_pln
    if from_ccy == "PLN" and to_ccy == "GBP" and usd_pln:
        return 1.0 / usd_pln
    if from_ccy == "PLN" and to_ccy == "USD" and usd_pln:
        return 1.0 / usd_pln
    if from_ccy == "USD" and to_ccy == "PLN" and usd_pln:
        return usd_pln

    # Triangulate via USD for currencies without direct {ccy}PLN pair
    if from_ccy in TRIANGULATE_VIA_USD and to_ccy == "PLN":
        ccy_usd = _rate(f"{from_ccy}USD")
        if ccy_usd and usd_pln:
            return ccy_usd * usd_pln
    if to_ccy in TRIANGULATE_VIA_USD and from_ccy == "PLN":
        ccy_usd = _rate(f"{to_ccy}USD")
        if ccy_usd and usd_pln and ccy_usd != 0:
            return 1.0 / (ccy_usd * usd_pln)

    # General triangulation via USD for any unsupported cross pair
    if from_ccy not in ("USD", to_ccy) and to_ccy not in ("USD", from_ccy):
        from_usd = _rate(f"{from_ccy}USD") if f"{from_ccy}USD" in FX_YAHOO else None
        to_usd   = _rate(f"{to_ccy}USD") if f"{to_ccy}USD" in FX_YAHOO else None
        if from_usd and to_usd and to_usd != 0:
            return from_usd / to_usd

    # Triangulate any two non-PLN currencies via their PLN pairs
    if from_ccy != "PLN" and to_ccy != "PLN":
        a = _rate(f"{from_ccy}PLN")
        b = _rate(f"{to_ccy}PLN")
        if a and b and a != 0:
            return a / b

    log.warning("FX rate %s→%s unavailable for %s, assuming 1.0", from_ccy, to_ccy, on_date)
    return 1.0  # last-resort fallback
