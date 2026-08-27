"""
transactions.py — transaction ledger management

transactions.jsonl schema (one object per line, chronological):
  {"date": "YYYY-MM-DD", "entries": [
      {"ticker": STR, "amount": FLOAT, "account_operation": BOOL}, ...
  ]}

  account_operation (optional, per entry): marks deposits/withdrawals
  that count toward invested capital.

balance.json schema:
  {"AAPL": 10.0, "PLN": 5000.0, ...}

Rules:
- File must stay chronological (ascending date).
- Inserting a transaction for an existing date: merge entries into that line.
- Inserting for a date earlier than the last line: find the correct position,
  insert, rewrite file, then invalidate portfolio cache from that date.
- Inserting for a new date after all existing: append.
"""
from __future__ import annotations

from datetime import date, timedelta

import storage
import config as cfg_module
from ticker_translate import translate_ticker
from ticker_data import get_price


def _apply_entries(balance: dict[str, dict], entries: list[dict]) -> None:
    for e in entries:
        ticker = e["ticker"].upper()
        amount = float(e["amount"])
        if ticker not in balance:
            balance[ticker] = {"amount": 0.0, "avg_price": 0.0}
        balance[ticker]["amount"] = balance[ticker]["amount"] + amount
        if abs(balance[ticker]["amount"]) < 1e-9:
            balance[ticker]["amount"] = 0.0
            balance[ticker]["avg_price"] = 0.0


def add_transaction(
    tx_date: date | str,
    entries: list[dict],
    account_operation: bool = False,
) -> None:
    """
    Add a transaction for the given date.

    entries: [{"ticker": "AAPL", "amount": 10.0}, {"ticker": "USD", "amount": -1710.0}]
    account_operation: if True, every entry gets account_operation=True
                       (marks deposits/withdrawals that count as invested).
    """
    if isinstance(tx_date, date):
        date_str = tx_date.isoformat()
    else:
        date_str = tx_date

    # Normalise
    rules = cfg_module.load().get("ticker_rules", [])
    entries = [
        {"ticker": translate_ticker(e["ticker"], rules), "amount": round(float(e["amount"]), 8),
         **({"account_operation": True} if account_operation or e.get("account_operation") else {})}
        for e in entries
    ]

    records = storage.read_jsonl(storage.TRANSACTIONS_PATH)

    if not records:
        storage.append_jsonl(storage.TRANSACTIONS_PATH, {"date": date_str, "entries": entries})
        _rebuild_balance([{"date": date_str, "entries": entries}])
        storage.invalidate_portfolio_from(date_str)
        return

    last_date = records[-1]["date"]

    if date_str > last_date:
        # Fast append — new date after everything
        rec = {"date": date_str, "entries": entries}
        storage.append_jsonl(storage.TRANSACTIONS_PATH, rec)
        today_str = date.today().isoformat()
        if date_str <= today_str:
            bal = storage.load_balance()
            base_ccy = cfg_module.load().get("default_currency", "PLN")
            _update_avg_prices(bal, rec, base_ccy)
            _apply_entries(bal, entries)
            storage.save_balance(bal)
        storage.invalidate_portfolio_from(date_str)
        return

    if date_str == last_date:
        # Merge into the last record
        records[-1]["entries"].extend(entries)
        storage.write_jsonl(storage.TRANSACTIONS_PATH, records)
        _rebuild_balance(records, from_date=date_str)
        storage.invalidate_portfolio_from(date_str)
        return

    # Past date — find insertion point, rewrite whole file
    new_records: list[dict] = []
    inserted = False
    for rec in records:
        if not inserted:
            if rec["date"] == date_str:
                # Merge into existing entry for this date
                rec = dict(rec)  # shallow copy to avoid mutating original
                rec["entries"] = rec["entries"] + entries
                new_records.append(rec)
                inserted = True
                continue
            elif rec["date"] > date_str:
                # Insert before this record
                new_records.append({"date": date_str, "entries": entries})
                inserted = True
        new_records.append(rec)

    if not inserted:
        new_records.append({"date": date_str, "entries": entries})

    storage.write_jsonl(storage.TRANSACTIONS_PATH, new_records)
    _rebuild_balance(new_records, from_date=date_str)
    storage.invalidate_portfolio_from(date_str)


def set_account_operation(date_str: str, entry_idx: int, value: bool) -> None:
    """Set or clear the account_operation flag on a specific entry.

    entry_idx: index of the entry within the transaction's entries list.
    """
    records = storage.read_jsonl(storage.TRANSACTIONS_PATH)
    for rec in records:
        if rec["date"] == date_str:
            entries = rec["entries"]
            if 0 <= entry_idx < len(entries):
                if value:
                    entries[entry_idx]["account_operation"] = True
                else:
                    entries[entry_idx].pop("account_operation", None)
                storage.write_jsonl(storage.TRANSACTIONS_PATH, records)
                storage.invalidate_portfolio_from(date_str)
            break


def delete_transaction(date_str: str, entry_idx: int) -> None:
    """Remove a single entry from a transaction. Removes the record if empty."""
    records = storage.read_jsonl(storage.TRANSACTIONS_PATH)
    new_records: list[dict] = []
    for rec in records:
        if rec["date"] == date_str:
            if 0 <= entry_idx < len(rec["entries"]):
                rec["entries"].pop(entry_idx)
                if rec["entries"]:
                    new_records.append(rec)
            else:
                new_records.append(rec)
        else:
            new_records.append(rec)
    storage.write_jsonl(storage.TRANSACTIONS_PATH, new_records)
    _rebuild_balance(new_records)
    storage.invalidate_portfolio_from(date_str)


def update_transaction(
    date_str: str,
    entry_idx: int,
    ticker: str,
    amount: float,
    account_operation: bool = False,
) -> None:
    """Replace a single entry's ticker, amount, and account_operation flag."""
    rules = cfg_module.load().get("ticker_rules", [])
    records = storage.read_jsonl(storage.TRANSACTIONS_PATH)
    for rec in records:
        if rec["date"] == date_str:
            if 0 <= entry_idx < len(rec["entries"]):
                new_entry: dict = {
                    "ticker": translate_ticker(ticker.upper(), rules),
                    "amount": round(float(amount), 8),
                }
                if account_operation:
                    new_entry["account_operation"] = True
                rec["entries"][entry_idx] = new_entry
                storage.write_jsonl(storage.TRANSACTIONS_PATH, records)
                _rebuild_balance(records)
                storage.invalidate_portfolio_from(date_str)
            break


def _rebuild_balance(records: list[dict], from_date: str | None = None) -> None:
    """Replay ledger to recompute balance and avg_price from scratch.

    If from_date is provided, only records on or after from_date are replayed
    on top of the existing balance. Otherwise replays everything from scratch.
    """
    base_ccy = cfg_module.load().get("default_currency", "PLN")
    today_str = date.today().isoformat()

    if from_date:
        balance = storage.load_balance()
        start_idx = 0
        for i, rec in enumerate(records):
            if rec["date"] >= from_date:
                start_idx = i
                break
        records = records[start_idx:]
    else:
        balance = {}

    price_cache: dict = {}
    for rec in records:
        if rec["date"] > today_str:
            continue
        _update_avg_prices(balance, rec, base_ccy, price_cache)
        _apply_entries(balance, rec["entries"])
    storage.save_balance(balance)


def _update_avg_prices(balance: dict[str, dict], rec: dict, base_ccy: str, price_cache: dict | None = None) -> None:
    """After applying entries, compute avg_price in base currency for stock buys.

    Uses the ticker's close price on the transaction date to determine cost.
    On sells, avg_price stays constant (standard weighted-average cost).
    """
    entries = rec["entries"]
    tx_date = rec["date"]
    yr = int(tx_date[:4])
    if price_cache is None:
        price_cache = {}

    # Accumulate cost and shares per ticker for this transaction
    ticker_cost: dict[str, float] = {}
    ticker_shares: dict[str, float] = {}

    for e in entries:
        ticker = e["ticker"].upper()
        amt = float(e["amount"])
        if ticker in storage.SUPPORTED_CURRENCIES or amt <= 0:
            continue

        close = get_price(ticker, tx_date, price_cache, yr)
        if close is None:
            continue

        ticker_cost[ticker] = ticker_cost.get(ticker, 0.0) + amt * close
        ticker_shares[ticker] = ticker_shares.get(ticker, 0.0) + amt

    # Collect all tickers touched by this transaction (buys + sells)
    all_tickers = set(ticker_shares.keys())
    for e in entries:
        t = e["ticker"].upper()
        if t not in storage.SUPPORTED_CURRENCIES:
            all_tickers.add(t)

    # Compute new avg_price
    # balance still has pre-tx state since _apply_entries hasn't run yet
    for ticker in all_tickers:
        pre = balance.get(ticker, {}).get("amount", 0.0)
        old_avg = balance.get(ticker, {}).get("avg_price", 0.0)

        net_change = sum(float(e["amount"]) for e in entries
                         if e["ticker"].upper() == ticker)
        new_amount = pre + net_change
        if new_amount > 0:
            old_cost = pre * old_avg
            if ticker in ticker_cost:
                # Buy: blend old cost with new cost
                new_cost = old_cost + ticker_cost[ticker]
            else:
                # Sell only: reduce cost pool proportionally
                new_cost = old_avg * new_amount
            new_avg = new_cost / new_amount
        else:
            new_avg = 0.0

        if ticker not in balance:
            balance[ticker] = {"amount": 0.0, "avg_price": new_avg}
        else:
            balance[ticker]["avg_price"] = new_avg


def rebuild_balance() -> None:
    """Rebuild balance.json from scratch by replaying the entire ledger."""
    records = get_all_transactions()
    _rebuild_balance(records)


def compute_cagr(current_value: float, base_currency: str | None = None, fx_cache: dict | None = None) -> float | None:
    """Compute Compound Annual Growth Rate from first deposit to now.

    current_value must be expressed in the same currency as base_currency
    (the portfolio snapshot's total_value). Falls back to config's
    default_currency when base_currency is not given.

    Returns CAGR as a decimal (e.g. 0.12 for 12%), or None if not enough data.
    """
    from ticker_data import get_fx_rate
    from datetime import date as _date

    records = get_all_transactions()
    if base_currency is None:
        base_currency = cfg_module.load().get("default_currency", "PLN")
    base_ccy = base_currency.upper()
    today = _date.today()
    if fx_cache is None:
        fx_cache = {}

    first_date = None
    net_invested = 0.0
    for rec in records:
        entries_list = rec["entries"]
        all_cash = all(
            e["ticker"].upper() in storage.SUPPORTED_CURRENCIES
            for e in entries_list
        )
        for e in entries_list:
            is_entry_op = e.get("account_operation", False)
            t = e["ticker"].upper()
            amt = float(e["amount"])
            if is_entry_op or (all_cash and t in storage.SUPPORTED_CURRENCIES):
                fx = get_fx_rate(t, base_ccy, rec["date"], fx_cache, int(rec["date"][:4])) if t != base_ccy else 1.0
                net_invested += amt * fx
                if first_date is None:
                    first_date = rec["date"]

    if first_date is None or net_invested <= 0:
        return None

    years = (today - _date.fromisoformat(first_date)).days / 365.25
    if years <= 0:
        return None

    return (current_value / net_invested) ** (1.0 / years) - 1.0


def compute_irr(current_value: float, base_currency: str | None = None, fx_cache: dict | None = None) -> float | None:
    """Compute Internal Rate of Return (money-weighted) using all cash flows.

    Deposits are negative (money out of pocket), withdrawals positive.
    The current portfolio value is the final positive cash flow.
    current_value must be expressed in the same currency as base_currency
    (the portfolio snapshot's total_value). Falls back to config's
    default_currency when base_currency is not given.

    Returns IRR as a decimal (e.g. 0.12 for 12%), or None if not solvable.
    """
    from ticker_data import get_fx_rate
    from datetime import date as _date

    records = get_all_transactions()
    if base_currency is None:
        base_currency = cfg_module.load().get("default_currency", "PLN")
    base_ccy = base_currency.upper()
    today = _date.today()
    if fx_cache is None:
        fx_cache = {}

    cash_flows: list[tuple[str, float]] = []
    for rec in records:
        for e in rec["entries"]:
            is_entry_op = e.get("account_operation", False)
            if not is_entry_op:
                continue
            t = e["ticker"].upper()
            amt = float(e["amount"])
            fx = get_fx_rate(t, base_ccy, rec["date"], fx_cache, int(rec["date"][:4])) if t != base_ccy else 1.0
            # Negate: positive account_op = deposit (money out of pocket)
            cash_flows.append((rec["date"], -amt * fx))

    if not cash_flows:
        return None

    # Merge cash flows on the same date
    merged: dict[str, float] = {}
    for d, amt in cash_flows:
        merged[d] = merged.get(d, 0.0) + amt

    # Add current portfolio value as final cash flow (positive — you own it)
    cf_list = sorted(merged.items())
    cf_list.append((today.isoformat(), current_value))

    # Convert dates to years from first cash flow
    start = _date.fromisoformat(cf_list[0][0])
    cf_years = [(_date.fromisoformat(d) - start).days / 365.25 for d, _ in cf_list]
    cf_amounts = [a for _, a in cf_list]

    def npv(rate: float) -> float:
        return sum(a / (1.0 + rate) ** t for a, t in zip(cf_amounts, cf_years))

    def npv_deriv(rate: float) -> float:
        return sum(-t * a / (1.0 + rate) ** (t + 1) for a, t in zip(cf_amounts, cf_years))

    # Newton-Raphson with bisection fallback
    rate = 0.1
    for _ in range(100):
        f = npv(rate)
        if abs(f) < 0.001:
            return rate
        fp = npv_deriv(rate)
        if abs(fp) < 1e-12:
            break
        new_rate = rate - f / fp
        if new_rate < -0.5:
            new_rate = -0.5
        if new_rate > 5.0:
            new_rate = 5.0
        rate = new_rate

    # Bisection fallback
    lo, hi = -0.5, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
        if abs(hi - lo) < 1e-8:
            break
    return (lo + hi) / 2.0


def get_all_transactions() -> list[dict]:
    """Return all transactions, chronologically (cached per file mtime)."""
    import os
    path = storage.TRANSACTIONS_PATH
    mtime = os.path.getmtime(path) if path.exists() else 0.0
    cache_key = ("_tx_cache", mtime)
    if cache_key not in get_all_transactions._cache:
        get_all_transactions._cache.clear()
        get_all_transactions._cache[cache_key] = storage.read_jsonl(path)
    return get_all_transactions._cache[cache_key]

get_all_transactions._cache: dict = {}


def get_transactions_up_to(as_of: str) -> list[dict]:
    """Return all transactions with date <= as_of."""
    return [r for r in get_all_transactions() if r["date"] <= as_of]


def compute_holdings_at(as_of: str) -> dict[str, float]:
    """
    Compute {ticker: amount} by replaying all transactions up to as_of.
    Returns only non-zero holdings (|amount| > 1e-9).
    """
    balance: dict[str, dict] = {}
    for rec in get_all_transactions():
        if rec["date"] > as_of:
            break
        _apply_entries(balance, rec["entries"])
    return {k: v["amount"] for k, v in balance.items() if abs(v["amount"]) > 1e-9}


def get_tickers(include_cash: bool = False) -> set[str]:
    """Return all unique non-cash tickers present in the ledger."""
    tickers: set[str] = set()
    for rec in get_all_transactions():
        for e in rec["entries"]:
            t = e["ticker"].upper()
            if include_cash or t not in storage.SUPPORTED_CURRENCIES:
                tickers.add(t)
    return tickers


def get_all_tickers(include_fx: bool = True) -> set[str]:
    """Return all tickers including FX pairs needed for price data."""
    tickers: set[str] = set()
    cash_currencies: set[str] = set()
    for rec in get_all_transactions():
        for e in rec["entries"]:
            t = e["ticker"].upper()
            if t in storage.SUPPORTED_CURRENCIES:
                cash_currencies.add(t)
            else:
                tickers.add(t)
    if include_fx:
        if "USD" in cash_currencies or tickers:
            tickers.add("USDPLN")
        if "EUR" in cash_currencies:
            tickers.add("EURPLN")
            tickers.add("EURUSD")
        for ccy, suffixes in storage.CURRENCY_SUFFIXES.items():
            if ccy == "PLN":
                continue
            if not any(t.upper().endswith(s) for t in tickers for s in suffixes):
                continue
            if ccy in storage.TRIANGULATE_VIA_USD:
                tickers.add(f"{ccy}USD")
            else:
                tickers.add(f"{ccy}PLN")
    return tickers


def existing_keys() -> set[tuple[str, str, float]]:
    """Return set of (date, ticker, amount) tuples from the ledger for dedup."""
    keys: set[tuple[str, str, float]] = set()
    for rec in get_all_transactions():
        for e in rec["entries"]:
            keys.add((rec["date"], e["ticker"].upper(), round(e["amount"], 8)))
    return keys


def get_ticker_history(ticker: str) -> list[dict]:
    """Return chronological buy/sell history for a single ticker.

    Scans the full ledger and returns one dict per matching entry:
      {date, amount, side, account_operation, running}
    where:
      - amount > 0 = buy, < 0 = sell
      - side is "Buy" / "Sell"
      - running is the cumulative position after this trade
    Cash / supported-currency entries are excluded.
    """
    ticker = ticker.upper()
    results: list[dict] = []
    running = 0.0
    for rec in get_all_transactions():
        for e in rec["entries"]:
            if e["ticker"].upper() != ticker:
                continue
            if ticker in storage.SUPPORTED_CURRENCIES:
                continue
            amt = float(e["amount"])
            if abs(amt) < 1e-12:
                continue
            running += amt
            results.append({
                "date": rec["date"],
                "amount": amt,
                "side": "Buy" if amt > 0 else "Sell",
                "account_operation": bool(e.get("account_operation", False)),
                "running": running,
            })
    return results


def fix_negative_positions(transactions: list[dict], currency: str) -> None:
    """If any stock/ETF ends negative, insert a buy on the same date to zero it."""
    balance: dict[str, float] = {}
    for rec in transactions:
        for e in rec["entries"]:
            ticker = e["ticker"].upper()
            if ticker in storage.SUPPORTED_CURRENCIES:
                continue
            balance[ticker] = balance.get(ticker, 0.0) + float(e["amount"])

    for ticker, amt in balance.items():
        if amt < -1e-9:
            # Find the date where the position first went negative
            fix_date = "2000-01-01"
            running: dict[str, float] = {}
            for rec in transactions:
                for e in rec["entries"]:
                    t = e["ticker"].upper()
                    if t in storage.SUPPORTED_CURRENCIES:
                        continue
                    running[t] = running.get(t, 0.0) + float(e["amount"])
                if running.get(ticker, 0.0) < -1e-9:
                    fix_date = rec["date"]
                    break
            buy_shares = round(abs(amt), 8)
            transactions.append({
                "date": fix_date,
                "entries": [
                    {"ticker": ticker, "amount": buy_shares},
                    {"ticker": currency, "amount": -0.01},
                ],
            })
