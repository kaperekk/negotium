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
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Callable

import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)


@contextmanager
def _suppress_output():
    """Suppress stdout/stderr to silence yfinance download noise."""
    devnull = open(os.devnull, "w")
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = devnull, devnull
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        devnull.close()

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
                print(f"[ticker_data] WARNING: could not download {symbol} {year}: {exc}")
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
    """
    if ticker.upper() in SUPPORTED_CURRENCIES:
        return  # cash holds its own value

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


def get_fx_rate(
    from_ccy: str,
    to_ccy: str,
    on_date: str,
    cache: dict,
    year: int,
) -> float:
    """
    Return exchange rate from_ccy → to_ccy on on_date.
    Falls back to 1.0 if same currency or rate unavailable.
    """
    if from_ccy == to_ccy:
        return 1.0

    pair = f"{from_ccy}{to_ccy}"
    reverse = f"{to_ccy}{from_ccy}"

    # Try direct pair
    if pair in FX_YAHOO:
        rate = get_price(pair, on_date, cache, year)
        if rate is not None:
            return rate

    # Try reverse pair
    if reverse in FX_YAHOO:
        rate = get_price(reverse, on_date, cache, year)
        if rate is not None and rate != 0:
            return 1.0 / rate

    # Triangulate via USD for currencies without direct pair
    usd_pln = get_price("USDPLN", on_date, cache, year)
    eur_usd = get_price("EURUSD", on_date, cache, year)

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
        ccy_usd = get_price(f"{from_ccy}USD", on_date, cache, year)
        if ccy_usd and usd_pln:
            return ccy_usd * usd_pln
    if to_ccy in TRIANGULATE_VIA_USD and from_ccy == "PLN":
        ccy_usd = get_price(f"{to_ccy}USD", on_date, cache, year)
        if ccy_usd and usd_pln and ccy_usd != 0:
            return 1.0 / (ccy_usd * usd_pln)

    # General triangulation via USD for any unsupported cross pair
    if from_ccy not in ("USD", to_ccy) and to_ccy not in ("USD", from_ccy):
        from_usd = get_price(f"{from_ccy}USD", on_date, cache, year) if f"{from_ccy}USD" in FX_YAHOO else None
        to_usd = get_price(f"{to_ccy}USD", on_date, cache, year) if f"{to_ccy}USD" in FX_YAHOO else None
        if from_usd and to_usd and to_usd != 0:
            return from_usd / to_usd

    return 1.0  # last-resort fallback
