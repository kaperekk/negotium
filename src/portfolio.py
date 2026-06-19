"""
portfolio.py — build the portfolio value time-series

portfolio.jsonl schema (one object per line, chronological):
  {
    "date": "YYYY-MM-DD",
    "assets": [
      {"ticker": "AAPL", "amount": 10.0, "price": 214.5, "currency": "USD",
       "value_native": 2145.0, "value_base": 8750.0},
      ...
    ],
    "total_value": 14300.0,       <- in base currency
    "invested": 12000.0,      <- cumulative net deposits in base currency
    "base_currency": "PLN"
  }

invested rule:
  Entries marked ``account_operation`` (deposits, withdrawals) always count
  toward invested capital.  Unmarked pure-cash transactions also count.
  Stock buys/sells never count — even if their cash leg is positive.
  - PLN +5000  (account_operation)       -> deposit, counts
  - PLN -2000  (account_operation)       -> withdrawal, counts
  - AAPL +10, USD -1700                  -> stock buy, neither counts
  - AAPL -10, USD +2100                  -> stock sell, neither counts
  - PLN +10000 (account_operation), AAPL +10, USD -1700
      -> deposit counts, stock buy does not

Key optimisations:
  1. Single forward pass: O(days + tx) not O(days x tx).
  2. _PriceCache loads each ticker-year slab once per build, never twice.
  3. Binary orjson I/O in storage layer.
  4. Resume: only days after last cached snapshot are recomputed.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from storage import (
    load_portfolio,
    save_portfolio,
    SUPPORTED_CURRENCIES,
    SUFFIX_CURRENCY,
)
from ticker_data import get_price, get_fx_rate, FX_YAHOO
from transactions import get_all_transactions

FX_TICKERS = set(FX_YAHOO.keys())


# -- Price cache ---------------------------------------------------------------

class _PriceCache:
    """
    Lazy per-ticker, per-year price slab.
    Loads each (ticker, year) pair exactly once per build_portfolio() call.
    """
    def __init__(self):
        self._data: dict[str, dict[int, dict[str, float]]] = {}

    def get(self, ticker: str, day: str, year: int) -> float | None:
        if ticker in SUPPORTED_CURRENCIES:
            return 1.0
        return get_price(ticker, day, self._data, year)

    def get_fx(self, from_ccy: str, to_ccy: str, day: str, year: int) -> float:
        return get_fx_rate(from_ccy, to_ccy, day, self._data, year)


# -- Ticker currency detection -------------------------------------------------

def _ticker_currency(ticker: str) -> str:
    t = ticker.upper()
    if t in SUPPORTED_CURRENCIES:
        return t
    ext = t[t.rfind("."):] if "." in t else ""
    ccy = SUFFIX_CURRENCY.get(ext)
    if ccy:
        return ccy
    if t in FX_TICKERS:
        return "PLN"
    if ext:
        print(f"[portfolio] WARNING: unknown exchange suffix '{ext}' for ticker {t}, assuming USD")
    return "USD"


# -- Main build function -------------------------------------------------------

def build_portfolio(
    start_date: date,
    end_date: date,
    base_currency: str,
    precision: str,                               # "D" or "W-FRI"
    progress_cb: Callable[[str, float], None] | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """
    Build or resume the portfolio value time-series.

    Single forward pass: O(days + transactions).
    Returns list of snapshot dicts, chronological. Also persists to portfolio.jsonl.
    """
    base_currency = base_currency.upper()
    cache = _PriceCache()

    # -- Resume from cache -----------------------------------------------------
    existing: list[dict] = []
    if use_cache:
        existing = [s for s in load_portfolio()
                    if s.get("base_currency") == base_currency]

    if existing:
        last_cached        = existing[-1]["date"]
        resume_from        = date.fromisoformat(last_cached) + timedelta(days=1)
        last_snap          = existing[-1]
        balance: dict[str, float] = {
            a["ticker"]: a["amount"] for a in last_snap["assets"]
        }
        cumulative_contrib = last_snap["invested"]
    else:
        resume_from        = start_date
        balance            = {}
        cumulative_contrib = 0.0

    # -- Load transactions once ------------------------------------------------
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    all_tx     = get_all_transactions()
    resume_str = resume_from.isoformat()
    pending_tx = [r for r in all_tx if r["date"] >= resume_str and r["date"] <= yesterday_str]
    tx_idx     = 0
    n_tx       = len(pending_tx)

    # -- Day iteration (forward pass) ------------------------------------------
    all_days      = list(_day_range(resume_from, end_date, precision))
    total_days    = max(len(all_days), 1)
    new_snapshots: list[dict] = []

    for i, day in enumerate(all_days):
        day_str = day.isoformat()
        year    = day.year

        if progress_cb and i % 10 == 0:
            progress_cb(day_str, i / total_days)

        # Apply pending transactions up to this day
        while tx_idx < n_tx and pending_tx[tx_idx]["date"] <= day_str:
            rec     = pending_tx[tx_idx]
            tx_year = int(rec["date"][:4])

            # invested rule:
            # Entries marked account_operation (deposits, withdrawals)
            # always count toward invested capital.
            # Unmarked pure-cash transactions (no stock entries) also count.
            # Stock buys/sells never count.
            entries_list = rec["entries"]
            all_cash = all(
                e["ticker"].upper() in SUPPORTED_CURRENCIES
                for e in entries_list
            )

            for e in entries_list:
                t   = e["ticker"].upper()
                amt = float(e["amount"])
                balance[t] = balance.get(t, 0.0) + amt

                is_entry_op = e.get("account_operation", False)
                if is_entry_op or (all_cash and t in SUPPORTED_CURRENCIES):
                    fx = cache.get_fx(t, base_currency, rec["date"], tx_year)
                    cumulative_contrib += amt * fx

            tx_idx += 1

        # Remove dust positions
        balance = {k: v for k, v in balance.items() if abs(v) > 1e-9}

        if not balance:
            new_snapshots.append({
                "date": day_str, "assets": [],
                "total_value": 0.0, "invested": 0.0,
                "base_currency": base_currency,
            })
            continue

        # Value each position
        assets      = []
        total_value = 0.0

        for ticker, amount in balance.items():
            t = ticker.upper()
            if t in FX_TICKERS:
                continue                       # internal FX helper, not displayed

            if t in SUPPORTED_CURRENCIES:
                rate       = cache.get_fx(t, base_currency, day_str, year)
                value_base = round(amount * rate, 2)
                assets.append({
                    "ticker":       t,
                    "amount":       round(amount, 8),
                    "price":        1.0,
                    "currency":     t,
                    "value_native": round(amount, 2),
                    "value_base":   value_base,
                })
                total_value += value_base
            else:
                price = cache.get(t, day_str, year)
                if price is None:
                    continue
                ticker_ccy   = _ticker_currency(t)
                value_native = round(amount * price, 2)
                rate         = cache.get_fx(ticker_ccy, base_currency, day_str, year)
                value_base   = round(value_native * rate, 2)
                assets.append({
                    "ticker":       t,
                    "amount":       round(amount, 8),
                    "price":        round(price, 6),
                    "currency":     ticker_ccy,
                    "value_native": value_native,
                    "value_base":   value_base,
                })
                total_value += value_base

        new_snapshots.append({
            "date":          day_str,
            "assets":        assets,
            "total_value":   round(total_value, 2),
            "invested":  round(cumulative_contrib, 2),
            "base_currency": base_currency,
        })

    if progress_cb:
        progress_cb(end_date.isoformat(), 1.0)

    # -- Merge, deduplicate, persist -------------------------------------------
    merged = _merge_snapshots(existing, new_snapshots)
    save_portfolio(merged)
    return merged


def _merge_snapshots(existing: list[dict], new: list[dict]) -> list[dict]:
    if not existing:
        return new
    if not new:
        return existing
    seen: dict[str, dict] = {s["date"]: s for s in existing}
    for s in new:
        seen[s["date"]] = s
    return sorted(seen.values(), key=lambda x: x["date"])


# -- Day range generator -------------------------------------------------------

def _day_range(start: date, end: date, precision: str):
    if precision == "D":
        d = start
        while d <= end:
            yield d
            d += timedelta(days=1)
    else:
        d = start
        d += timedelta(days=(4 - d.weekday()) % 7)   # jump to first Friday
        while d <= end:
            yield d
            d += timedelta(weeks=1)


# -- Series extraction ---------------------------------------------------------

def snapshots_to_series(snapshots: list[dict]) -> tuple[list[str], list[float], list[float]]:
    dates  = [s["date"]         for s in snapshots]
    values = [s["total_value"]  for s in snapshots]
    contrs = [s["invested"] for s in snapshots]
    return dates, values, contrs
